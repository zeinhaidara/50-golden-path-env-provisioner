module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "6.8.0"

  name            = var.name
  cidr            = var.vpc_cidr
  azs             = var.availability_zones
  private_subnets = var.private_subnets
  public_subnets  = var.public_subnets

  # One NAT gateway keeps a dev environment cheap; use one per AZ for prod.
  enable_nat_gateway = true
  single_nat_gateway = true

  public_subnet_tags  = { "kubernetes.io/role/elb" = "1" }
  private_subnet_tags = { "kubernetes.io/role/internal-elb" = "1" }
}

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "21.30.2"

  name               = var.name
  kubernetes_version = var.kubernetes_version
  vpc_id             = module.vpc.vpc_id
  subnet_ids         = module.vpc.private_subnets

  # The workflow's Ansible step needs the API; only listed CIDRs can reach it.
  endpoint_public_access       = true
  endpoint_public_access_cidrs = var.api_allowed_cidrs

  enable_cluster_creator_admin_permissions = true

  addons = {
    coredns    = {}
    kube-proxy = {}
    vpc-cni = {
      before_compute = true
    }
    eks-pod-identity-agent = {
      before_compute = true
    }
    # Observability add-on: CloudWatch agent + Fluent Bit, managed by EKS.
    amazon-cloudwatch-observability = {}
  }

  eks_managed_node_groups = {
    default = {
      instance_types = var.node_instance_types
      min_size       = var.node_min_size
      desired_size   = var.node_desired_size
      max_size       = var.node_max_size

      # Lets the CloudWatch agent on the nodes publish metrics and logs.
      iam_role_additional_policies = {
        cloudwatch = "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
      }
    }
  }
}
