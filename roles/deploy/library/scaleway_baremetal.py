#!/usr/bin/python
#
# Scaleway Compute management module
#
# Copyright (C) 2018 Online SAS.
# https://www.scaleway.com
#
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

#
#  THIS PLUGING IS NOT PROD READY, it's just a demonstration plugin !!!
#

from __future__ import absolute_import, division, print_function

__metaclass__ = type

ANSIBLE_METADATA = {
    'metadata_version': '1.1',
    'status': ['preview'],
    'supported_by': 'community'
}

DOCUMENTATION = '''
---
module: scaleway_baremetal
short_description: Scaleway baremetal instance management module
version_added: "2.6"
author: Loic PORTE (@bewiwi)
description:
    - "This module manages baremetal instances on Scaleway."
extends_documentation_fragment: scaleway

options:

  image:
    description:
      - Image identifier used to start the instance with
    required: true

  name:
    description:
      - Name of the instance

  organization:
    description:
      - Organization identifier
    required: true

  state:
    description:
     - Indicate desired state of the instance.
    default: ready
    choices:
      - absent
      - ready

  tags:
    description:
    - List of tags to apply to the instance (5 max)
    required: false
    default: []

  zone:
    description:
    - Scaleway compute zone
    required: true
    choices:
      - par2

  offer:
    description:
    - offer id of the instance node
    required: true

  wait_order:
    description:
    - Wait for the instance to be available before returning.
    type: bool
    default: 'no'

  wait_install:
    description:
    - Wait for the instance to be install before returning.
    type: bool
    default: 'no'

  wait_timeout:
    description:
    - Time to wait for the server to be delivered
    required: false
    default: 300

  wait_install_timeout:
    description:
    - Time to wait for the server to be installed
    required: false
    default: 300

  wait_sleep_time:
    description:
    - Time to wait before every attempt to check the state of the server
    required: false
    default: 3
'''

EXAMPLES = '''
- name: Create a server
  scaleway_baremetal:
    name: foobar
    state: ready
    image: 89ee4018-f8c3-4dc4-a6b5-bca14f985ebe
    organization: 951df375-e094-4d26-97c1-ba548eeb9c42
    region: par2
    offer: 9eebce52-f7d5-484f-9437-b234164c4c4b
    tags:
      - test
      - www

- name: Destroy it right after
  scaleway_compute:
    name: foobar
    state: absent
    image: 89ee4018-f8c3-4dc4-a6b5-bca14f985ebe
    organization: 951df375-e094-4d26-97c1-ba548eeb9c42
    region: par2
    offer: 9eebce52-f7d5-484f-9437-b234164c4c4b
    tags:
      - test
      - www

'''

RETURN = '''
'''

import datetime
import time

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.six.moves.urllib.parse import quote as urlquote
from ansible.module_utils.scaleway import scaleway_argument_spec, Scaleway

SCALEWAY_TRANSITIONS_STATES = [
    "undelivered",
    "stopping",
    "starting",
    "deleting",
]

SCALEWAY_INSTALLATION_TRANSITIONS_STATES = [
    "installing",
    "to_install",
]


def fetch_state(compute_api, server):
    compute_api.module.debug("fetch_state of server: %s" % server["id"])
    response = compute_api.get(path="servers/%s" % server["id"])

    if response.status_code == 404:
        return "absent"

    if not response.ok:
        msg = 'Error during state fetching: (%s) %s' % (response.status_code,
                                                        response.json)
        compute_api.module.fail_json(msg=msg)

    try:
        compute_api.module.debug("Server %s in state: %s" %
                                 (server["id"], response.json["status"]))
        return response.json["status"]
    except KeyError:
        compute_api.module.fail_json(msg="Could not fetch state in %s" %
                                     response.json)


def fetch_install_state(compute_api, server):
    compute_api.module.debug("fetch_install_state of server: %s" %
                             server["id"])
    response = compute_api.get(path="servers/%s" % server["id"])

    if response.status_code == 404:
        return "absent"

    if not response.ok:
        msg = 'Error during install state fetching: (%s) %s' % (
            response.status_code, response.json)
        compute_api.module.fail_json(msg=msg)

    try:
        state = response.json.get('install', {}).get('status')
        compute_api.module.debug("Server installation %s in state: %s" %
                                 (server["id"], state))
        return state
    except KeyError:
        compute_api.module.fail_json(
            msg="Could not fetch installation state in %s" % response.json)


def wait_to_complete_state_transition(compute_api, server):
    wait_order = compute_api.module.params["wait_order"]
    wait_install = compute_api.module.params["wait_install_timeout"]
    wait_timeout = compute_api.module.params["wait_timeout"]
    wait_sleep_time = compute_api.module.params["wait_sleep_time"]

    if not wait_install and not wait_order:
        return

    start = datetime.datetime.utcnow()
    end = start + datetime.timedelta(seconds=wait_timeout)
    while datetime.datetime.utcnow() < end:
        compute_api.module.debug(
            "We are going to wait for the server to finish its transition")
        status = fetch_state(compute_api, server)
        if status not in SCALEWAY_TRANSITIONS_STATES:
            compute_api.module.debug(
                "It seems that the server is not in transition anymore.")
            compute_api.module.debug("Server in state: %s" % status)
            break
        time.sleep(wait_sleep_time)
    else:
        compute_api.module.fail_json(
            msg="Server takes too long to finish its transition")


def wait_to_complete_install(compute_api, server):
    wait_order = compute_api.module.params["wait_order"]
    wait_install = compute_api.module.params["wait_install"]
    wait_timeout = compute_api.module.params["wait_install_timeout"]
    wait_sleep_time = compute_api.module.params["wait_sleep_time"]

    if not wait_install:
        return

    start = datetime.datetime.utcnow()
    end = start + datetime.timedelta(seconds=wait_timeout)
    while datetime.datetime.utcnow() < end:

        status = fetch_install_state(compute_api, server)
        if status not in SCALEWAY_INSTALLATION_TRANSITIONS_STATES:
            compute_api.module.debug(
                "It seems that the instalation is not in transition anymore.")
            compute_api.module.debug("Server instalation in state: %s" %
                                     status)
            break
        else:
            compute_api.module.debug(
                "We are going to wait for the instalation to finish its transition : %s"
                % status)
        time.sleep(wait_sleep_time)
    else:
        compute_api.module.fail_json(
            msg="Server instalation takes too long to finish its transition")


def create_server(compute_api, server):
    compute_api.module.debug("Starting a create_server")
    target_server = None
    payload = {
        "tags": server["tags"],
        "offer_id": server["offer"],
        "description": server["description"],
        "name": server["name"],
        "organization_id": server["organization"]
    }

    response = compute_api.post(path="servers", data=payload)

    if not response.ok:
        msg = 'Error during server creation: (%s) %s' % (response.status_code,
                                                         response.json)
        compute_api.module.fail_json(msg=msg)

    try:
        target_server = response.json
    except KeyError:
        compute_api.module.fail_json(
            msg="Error in getting the server information from: %s" %
            response.json)

    wait_to_complete_state_transition(compute_api=compute_api,
                                      server=target_server)

    return target_server


def remove_server(compute_api, server):
    compute_api.module.debug("Starting remove server strategy")
    response = compute_api.delete(path="servers/%s" % server["id"])
    if not response.ok:
        msg = 'Error during server deletion: (%s) %s' % (response.status_code,
                                                         response.json)
        compute_api.module.fail_json(msg=msg)

    wait_to_complete_state_transition(compute_api=compute_api, server=server)

    return response


def absent_strategy(compute_api, wished_server):
    compute_api.module.debug("Starting absent strategy")
    changed = False
    target_server = None
    query_results = find(compute_api=compute_api, wished_server=wished_server)

    if not query_results:
        return changed, {"status": "Server already absent."}
    else:
        target_server = query_results[0]

    changed = True

    if compute_api.module.check_mode:
        return changed, {
            "status": "Server %s would be made absent." % target_server["id"]
        }

    response = remove_server(compute_api=compute_api, server=target_server)

    if not response.ok:
        err_msg = 'Error while removing server [{0}: {1}]'.format(
            response.status_code, response.json)
        compute_api.module.fail_json(msg=err_msg)

    return changed, {"status": "Server %s deleted" % target_server["id"]}


def ready_strategy(compute_api, wished_server):
    compute_api.module.debug("Starting ready strategy")
    changed = False
    query_results = find(compute_api=compute_api, wished_server=wished_server)

    if not query_results:
        changed = True
        if compute_api.module.check_mode:
            return changed, {
                "status": "A server would be created before being run."
            }

        target_server = create_server(compute_api=compute_api,
                                      server=wished_server)
    else:
        target_server = query_results[0]

    if server_attributes_should_be_changed(compute_api=compute_api,
                                           target_server=target_server,
                                           wished_server=wished_server):
        changed = True

        if compute_api.module.check_mode:
            return changed, {
                "status":
                "Server %s attributes would be changed before ready it." %
                target_server["id"]
            }

        server_change_attributes(compute_api=compute_api,
                                 target_server=target_server,
                                 wished_server=wished_server)
    else:
        wait_to_complete_state_transition(compute_api=compute_api,
                                          server=target_server)
        wait_to_complete_install(compute_api, target_server)
    return changed, target_server


state_strategy = {"ready": ready_strategy, "absent": absent_strategy}


def find(compute_api, wished_server):
    compute_api.module.debug("Getting inside find")
    # Pagination is not handle for this demo
    url = 'servers?per_page=50'
    response = compute_api.get(url)

    if not response.ok:
        msg = 'Error during server search: (%s) %s' % (response.status_code,
                                                       response.json)
        compute_api.module.fail_json(msg=msg)

    search_results = None
    for server in response.json["servers"]:
        if server['name'] == wished_server[
                'name'] and server['status'] != 'deleting':
            compute_api.module.debug("found server : %s" % server)
            return [server]


PATCH_MUTABLE_SERVER_ATTRIBUTES = (
    "tags",
    "description",
)


def server_should_be_reinstall(compute_api, target_server, wished_server):

    if target_server.get('install') is None:
        compute_api.module.debug("Reinstall server cause no install on server")
        return True

    server_install = target_server.get('install', {})

    if wished_server['image'] and wished_server['image'] != server_install.get(
            'os_id'):
        compute_api.module.debug("Reinstall server cause image is different")
        return True

    if wished_server['ssh_key_ids'] and set(
            wished_server['ssh_key_ids']) != set(
                server_install.get('ssh_key_ids', [])):
        compute_api.module.debug(
            "Reinstall server cause ssh keys is different")
        return True

    return False


def server_attributes_should_be_changed(compute_api, target_server,
                                        wished_server):
    compute_api.module.debug("Checking if server attributes should be changed")
    compute_api.module.debug("Current Server: %s" % target_server)
    compute_api.module.debug("Wished Server: %s" % wished_server)
    debug_dict = dict((x, (target_server[x], wished_server[x]))
                      for x in PATCH_MUTABLE_SERVER_ATTRIBUTES
                      if x in target_server and x in wished_server)
    compute_api.module.debug("Debug dict %s" % debug_dict)

    try:
        if any([
                target_server[x] != wished_server[x]
                for x in PATCH_MUTABLE_SERVER_ATTRIBUTES
                if x in target_server and x in wished_server
        ]):
            return True
    except AttributeError:
        compute_api.module.fail_json(
            msg="Error while checking if attributes should be changed")

    return server_should_be_reinstall(compute_api, target_server,
                                      wished_server)


def server_change_attributes(compute_api, target_server, wished_server):
    compute_api.module.debug("Starting patching server attributes")
    patch_payload = dict((x, wished_server[x])
                         for x in PATCH_MUTABLE_SERVER_ATTRIBUTES
                         if x in wished_server and x in target_server)
    response = compute_api.patch(path="servers/%s" % target_server["id"],
                                 data=patch_payload)
    if not response.ok:
        msg = 'Error during server attributes patching: (%s) %s' % (
            response.status_code, response.json)
        compute_api.module.fail_json(msg=msg)

    wait_to_complete_state_transition(compute_api=compute_api,
                                      server=target_server)

    # install server if needed
    if server_should_be_reinstall(compute_api, target_server, wished_server):
        compute_api.module.params["wait_order"] = True
        wait_to_complete_state_transition(compute_api=compute_api,
                                          server=target_server)
        server_install(compute_api, target_server, wished_server)
    wait_to_complete_install(compute_api, target_server)
    return response


def server_install(compute_api, target_server, wished_server):
    compute_api.module.debug("Starting installation")
    payload = {
        "hostname": wished_server["name"],
        "os_id": wished_server["image"],
        "ssh_key_ids": wished_server["ssh_key_ids"]
    }
    response = compute_api.post(path="servers/%s/install" %
                                target_server["id"],
                                data=payload)
    if not response.ok:
        msg = 'Error during server installation: (%s) %s' % (
            response.status_code, response.json)
        compute_api.module.fail_json(msg=msg)


def core(module):
    zone = module.params["zone"]
    wished_server = {
        "state": module.params["state"],
        "image": module.params["image"],
        "name": module.params["name"],
        "offer": module.params["offer"],
        "tags": module.params["tags"],
        "description": module.params["description"],
        "organization": module.params["organization"],
        "ssh_key_ids": module.params["ssh_key_ids"]
    }
    module.params[
        'api_url'] = "https://api.scaleway.com/baremetal/v1alpha1/zones/{}".format(
            zone)

    compute_api = Scaleway(module=module)

    changed, summary = state_strategy[wished_server["state"]](
        compute_api=compute_api, wished_server=wished_server)
    module.exit_json(changed=changed, msg=summary)


def main():
    argument_spec = scaleway_argument_spec()
    argument_spec.update(
        dict(
            image=dict(required=True),
            name=dict(),
            description=dict(default=""),
            zone=dict(required=True, choices=['fr-par-2']),
            offer=dict(required=True),
            state=dict(choices=state_strategy.keys(), default='ready'),
            tags=dict(type="list", default=[]),
            organization=dict(required=True),
            wait_order=dict(type="bool", default=False),
            wait_install=dict(type="bool", default=False),
            wait_timeout=dict(type="int", default=1200),
            wait_sleep_time=dict(type="int", default=3),
            wait_install_timeout=dict(type="int", default=1500),
            ssh_key_ids=dict(type='list', default=[]),
        ))
    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=True,
    )

    core(module)


if __name__ == '__main__':
    main()
