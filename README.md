# Demo Scaleway Instance + baremetal nomad deployment

This repo contains ansible code to deploy consul clusters and nomad clusters on Scaleway infra compute and baremetal. This demo was created for the Scaleday.

## Run

Install python requirement 

```
pip install -r requirements.yml 
```

Install ansible module

```
ansible-galaxy install -r roles/requirements
```

You had to export your scaleway token in your env

```
export SCW_TOKEN: <mytoken>
```

Just run ansible-playbook to deploy and configure compute and baremetal instance

```
ansible-playbook site.yml -i inventory
```