# Ansible Scripts

Run script
```sh
export ANSIBLE_HOST_KEY_CHECKING=False
ansible-playbook configuraion.yml -i inventory.ini -l {group_or_host} --private-key={path_to_private_key}
```