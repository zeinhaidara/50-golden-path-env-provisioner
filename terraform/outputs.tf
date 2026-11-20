output "cluster_name" {
  description = "EKS cluster name, used by the workflow to fetch a kubeconfig."
  value       = module.eks.cluster_name
}

output "vpc_id" {
  description = "VPC ID."
  value       = module.vpc.vpc_id
}
