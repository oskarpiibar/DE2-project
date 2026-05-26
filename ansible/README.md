# Ansible Scripts

Run script
```sh
export ANSIBLE_HOST_KEY_CHECKING=False
ansible-playbook configuration.yml -i inventory.ini -l {group_or_host} --extra-vars "github_pat=ghp_xxxx" --private-key={path_to_private_key}
```