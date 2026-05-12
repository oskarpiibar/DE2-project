output "instance_names" {
  value = openstack_compute_instance_v2.vm[*].name
}

output "private_ips" {
  value = openstack_compute_instance_v2.vm[*].access_ip_v4
}

output "floating_ips" {
  value = openstack_networking_floatingip_v2.fip[*].address
}

# Also generate Ansible inventory automatically
resource "local_file" "ansible_inventory" {
  content = templatefile("${path.module}/inventory.tpl", {
    ips = [for ip in openstack_compute_instance_v2.vm : ip.access_ip_v4]
    env = var.environment
  })
  filename = "inventory.ini"
}