# Values come from build/<env>/terraform.tfvars.json, rendered from params/<env>.yaml.

variable "name" {
  description = "Name prefix, also the EKS cluster name."
  type        = string
}

variable "region" {
  description = "AWS region."
  type        = string
}

variable "allowed_account_ids" {
  description = "Guard against running against the wrong account."
  type        = list(string)
}

variable "vpc_cidr" {
  description = "VPC CIDR."
  type        = string
}

variable "availability_zones" {
  description = "AZs for subnets."
  type        = list(string)
}

variable "private_subnets" {
  description = "One private subnet per AZ (nodes)."
  type        = list(string)
}

variable "public_subnets" {
  description = "One public subnet per AZ (load balancers, NAT)."
  type        = list(string)
}

variable "kubernetes_version" {
  description = "EKS Kubernetes version."
  type        = string
}

variable "node_instance_types" {
  description = "Instance types for the managed node group."
  type        = list(string)
}

variable "node_min_size" {
  description = "Node group minimum size."
  type        = number
}

variable "node_desired_size" {
  description = "Node group desired size."
  type        = number
}

variable "node_max_size" {
  description = "Node group maximum size."
  type        = number
}

variable "api_allowed_cidrs" {
  description = "CIDRs allowed to reach the public EKS API endpoint."
  type        = list(string)
}

variable "tags" {
  description = "Default tags for every resource."
  type        = map(string)
}
