# Ansible Scripts

Run script
```sh
export ANSIBLE_HOST_KEY_CHECKING=False
ansible-playbook configuraion.yml -i inventory.ini --private-key={path_to_private_key}
```