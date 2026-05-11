variable "environment" {
  type = string
}

variable "replica_count" {
  type    = number
  default = 1
}

variable "image_id" {
  type = string
}

variable "flavor_name" {
  type = string
}

variable "key_pair" {
  type = string
}

variable "network_id" {
  type = string
}

variable "security_groups" {
  type    = list(string)
  default = ["default"]
}

variable "floating_ip_pool" {
  type = string
}

variable "assign_floating_ip" {
  type    = bool
  default = false
}