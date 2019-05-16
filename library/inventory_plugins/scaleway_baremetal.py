# Copyright (c) 2017 Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

#
#  THIS PLUGING IS NOT PROD READY, it's just a demonstration plugin!!!
#

from __future__ import (absolute_import, division, print_function)

__metaclass__ = type

DOCUMENTATION = '''
    name: scaleway_baremetal
    plugin_type: inventory
    author:
      - Loic PORTE (@bewiwi)
    short_description: Scaleway inventory source
    description:
        - Get inventory hosts from Scaleway
    options:
        plugin:
            description: token that ensures this is a source file for the 'scaleway_baremetal' plugin.
            required: True
            choices: ['scaleway_baremetal']
        zones:
            description: Filter results on a specific Scaleway region
            type: list
            default:
                - fr-par-2
        tags:
            description: Filter results on a specific tag
            type: list
        oauth_token:
            required: True
            description: Scaleway OAuth token.
            env:
                # in order of precedence
                - name: SCW_TOKEN
                - name: SCW_API_KEY
                - name: SCW_OAUTH_TOKEN
        names:
            description: List of preference about what to use as an name.
            type: list
            default:
                - public_ipv4
            choices:
                - public_ipv4
                - public_ipv6
                - name
                - id
        variables:
            description: 'set individual variables: keys are variable names and
                          values are templates. Any value returned by the
                          L(Scaleway API, https://developer.scaleway.com/#servers-server-get)
                          can be used.'
            type: dict
'''

EXAMPLES = '''
# scaleway_inventory.yml file in YAML format
# Example command line: ansible-inventory --list -i scaleway_inventory.yml

# use name as inventory_hostname and public IP address to connect to the host
plugin: scaleway_baremetal
names:
  - name
zones:
  - fr-par-2
variables:
  ansible_host: public_ip.address
'''

import json

from ansible.errors import AnsibleError
from ansible.plugins.inventory import BaseInventoryPlugin, Constructable
from ansible.module_utils.scaleway import SCALEWAY_LOCATION
from ansible.module_utils.urls import open_url
from ansible.module_utils._text import to_native


def _fetch_information(token, url):
    try:
        response = open_url(url,
                            headers={'X-Auth-Token': token,
                                     'Content-type': 'application/json'})
    except Exception as e:
        raise AnsibleError("Error while fetching %s: %s" % (url, to_native(e)))

    try:
        raw_json = json.loads(response.read())
    except ValueError:
        raise AnsibleError("Incorrect JSON payload")

    try:
        return raw_json["servers"]
    except KeyError:
        raise AnsibleError("Incorrect format from the Scaleway API response")


def _build_server_url(zone):
    return "https://api.scaleway.com/baremetal/v1alpha1/zones/{}/servers".format(zone)


def extract_public_ipv4(server_info):
    try:
        return [ip['address'] for ip in server_info["ips"] if ip["version"] == 'Ipv4'][0]
    except (KeyError, TypeError):
        return None


def extract_name(server_info):
    try:
        return server_info["name"]
    except (KeyError, TypeError):
        return None


def extract_server_id(server_info):
    try:
        return server_info["id"]
    except (KeyError, TypeError):
        return None


def extract_public_ipv6(server_info):
    try:
        return [ip['address'] for ip in server_info["ips"] if ip["version"] == 'Ipv6'][0]
    except (KeyError, TypeError):
        return None


def extract_tags(server_info):
    try:
        return server_info["tags"]
    except (KeyError, TypeError):
        return None


extractors = {
    "public_ipv4": extract_public_ipv4,
    "public_ipv6": extract_public_ipv6,
    "name": extract_name,
    "id": extract_server_id
}


class InventoryModule(BaseInventoryPlugin, Constructable):
    NAME = 'scaleway_baremetal'

    def _fill_host_variables(self, host, server_info):
        targeted_attributes = (
            "offer_id",
            "id",
            "organization_id",
            "status",
            "name",
            "install"
        )
        for attribute in targeted_attributes:
            self.inventory.set_variable(host, attribute, server_info[attribute])

        self.inventory.set_variable(host, "tags", server_info["tags"])

        if extract_public_ipv6(server_info=server_info):
            self.inventory.set_variable(host, "public_ipv6", extract_public_ipv6(server_info=server_info))

        if extract_public_ipv4(server_info=server_info):
            self.inventory.set_variable(host, "public_ipv4", extract_public_ipv4(server_info=server_info))

    def match_groups(self, server_info, tags):
        server_tags = extract_tags(server_info=server_info)

        # If no filtering is defined, all tags are valid groups
        if tags is None:
            return set(server_tags)

        matching_tags = set(server_tags).intersection(tags)

        if not matching_tags:
            return set()
        else:
            return matching_tags

    def _filter_host(self, host_infos, name_preferences):

        for pref in name_preferences:
            if extractors[pref](host_infos):
                return extractors[pref](host_infos)

        return None

    def do_zone_inventory(self, zone, token, tags, name_preferences):
        self.inventory.add_group(zone)

        url = _build_server_url(zone)
        raw_zone_hosts_infos = _fetch_information(url=url, token=token)

        for host_infos in raw_zone_hosts_infos:
            name = self._filter_host(host_infos=host_infos,
                                     name_preferences=name_preferences)
            # Hack to simplify user variables
            host_infos['public_ipv4'] = extract_public_ipv4(host_infos)
            host_infos['public_ipv6'] = extract_public_ipv6(host_infos)

            # No suitable name were found in the attributes and the host won't be in the inventory
            if not name:
                continue

            self.inventory.add_host(group=zone, host=name)
            groups = self.match_groups(host_infos, tags)

            for group in groups:
                self.inventory.add_group(group=group)
                self.inventory.add_host(group=group, host=name)
                self._fill_host_variables(host=name, server_info=host_infos)

                # Composed variables
                self._set_composite_vars(self.get_option('variables'), host_infos, name, strict=False)

    def parse(self, inventory, loader, path, cache=True):
        super(InventoryModule, self).parse(inventory, loader, path)
        self._read_config_data(path=path)
        config_zones = self.get_option("zones")
        tags = self.get_option("tags")
        token = self.get_option("oauth_token")
        name_preference = self.get_option("names")

        for zone in config_zones:
            self.do_zone_inventory(zone=zone, token=token, tags=tags, name_preferences=name_preference)
