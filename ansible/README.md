# Ansible Scripts

There are 2 Ansible script in this directory:

1. `configuration.yml` : fully configure dev servers and install required apps/packages for prod servers.
2. `deploy.yml` : deploy predictor app (frontend+backend), load balancer, and configure remote repository for git hooks.

### Prerequisite
1. Ansible installed, see [install ansible](../script/install/install_ansible.sh).
2. Create `inventory.ini` file, see [inventory.ini.example](./inventory.ini.example)

Run script
```sh
export ANSIBLE_HOST_KEY_CHECKING=False
ansible-playbook {script_name}.yml -i inventory.ini -l {group_or_host} --extra-vars "github_pat=ghp_xxxx" --private-key={path_to_private_key}

# example:
ansible-playbook configuration.yml -i inventory.ini -l all --extra-vars "github_pat=ghp_xxxx" --private-key=~/.ssh/my_key

ansible-playbook deploy.yml -i inventory.ini -l prod1 --extra-vars "github_pat=ghp_xxxx" --private-key=~/.ssh/my_key

```