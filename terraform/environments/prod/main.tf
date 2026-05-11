data "openstack_images_image_v2" "image" {
  name        = var.image_name
  most_recent = true
}

data "openstack_networking_network_v2" "network" {
  name = var.network_name
}

module "prod" {
  source = "../../modules/vm_group"

  environment        = "prod"
  replica_count      = var.replica_count
  image_id           = data.openstack_images_image_v2.image.id
  flavor_name        = var.flavor
  key_pair           = var.key_pair
  network_id         = data.openstack_networking_network_v2.network.id
  security_groups    = var.security_groups
  floating_ip_pool   = var.floating_ip_pool
  assign_floating_ip = var.assign_floating_ip
}