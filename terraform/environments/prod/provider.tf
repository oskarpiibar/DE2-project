terraform {
  required_providers {
    openstack = {
      source  = "terraform-provider-openstack/openstack"
      version = "~> 1.54.0"
    }
  }

  backend "local" {
    path = "terraform.tfstate"
  }
}

provider "openstack" {}
