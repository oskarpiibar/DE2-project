# Terraform scripts to provision prod and dev servers

## Prerequisites

1. Terraform installed (run [this script](../script/install_terraform.sh))
2. Openstack client installed (run [this script](../script/install_openstack_client.sh))
3. The RC file, download from OpenStack dashboard → API Access. Then source it by run command `source <name_of_rc_file>`


## How to run

```bash

# Always first
source <name_of_rc_file>

# Terraform workflow 
# Run below commands inside environments/prod (if you want to deploy prod vm) or environments/dev (if you want to deploy dev vm)
terraform init       # Download providers and modules
terraform plan       # Preview changes
terraform apply      # Apply changes
terraform output     # Show IPs and instance names

# Command to destroy instances
terraform destroy    # Remove all instances
```
