variable "image_name" {
  description = "OS image for prod VMs"
  type        = string
}

variable "flavor" {
  description = "Flavor for prod VMs"
  type        = string
}

variable "replica_count" {
  description = "Number of prod VM replicas"
  type        = number
}

variable "key_pair" {
  description = "Keypair name"
  type        = string
}

variable "network_name" {
  description = "Network name"
  type        = string
}

variable "security_groups" {
  description = "Security groups for prod"
  type        = list(string)
}

variable "floating_ip_pool" {
  description = "External network for floating IPs"
  type        = string
}

variable "assign_floating_ip" {
  description = "Whether to assign floating IPs"
  type        = bool
}