terraform {
  required_providers {
    openstack = {
      source  = "terraform-provider-openstack/openstack"
      version = "~> 1.54.0"
    }
  }
}

resource "openstack_compute_instance_v2" "vm" {
  count           = var.replica_count
  name            = "${var.environment}-group1-vm-${count.index + 1}"
  image_id        = var.image_id
  flavor_name     = var.flavor_name
  key_pair        = var.key_pair
  security_groups = var.security_groups

  network {
    uuid = var.network_id
  }

  metadata = {
    environment = var.environment
    replica     = count.index + 1
  }

  tags = [var.environment, "replica-${count.index + 1}"]
}

# Get floating IPs from the pool if assign_floating_ip is true
resource "openstack_networking_floatingip_v2" "fip" {
  count = var.assign_floating_ip ? var.replica_count : 0
  pool  = var.floating_ip_pool
}

# Associate floating IPs to VMs if assign_floating_ip is true
resource "openstack_compute_floatingip_associate_v2" "fip_assoc" {
  count       = var.assign_floating_ip ? var.replica_count : 0
  floating_ip = openstack_networking_floatingip_v2.fip[count.index].address
  instance_id = openstack_compute_instance_v2.vm[count.index].id
}