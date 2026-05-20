image_name         = "Ubuntu 22.04 - 2024.01.15"
flavor             = "ssc.medium"
replica_count      = 2 # how many VMs to create
key_pair           = "group1-key"
network_name       = "UPPMAX 2026/1-24 Internal IPv4 Network"
security_groups    = ["default"]
floating_ip_pool   = "public"
assign_floating_ip = false