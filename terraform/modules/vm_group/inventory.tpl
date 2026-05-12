[${env}]
%{ for i, ip in ips ~}
${env}${i + 1} ansible_host=${ip} ansible_connection=ssh ansible_user=ubuntu
%{ endfor ~}
