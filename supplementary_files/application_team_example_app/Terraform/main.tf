terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 4.0"
    }
  }
  backend "s3" {
    bucket  = "cschneider-terraform-backend-02" #RER
    key     = "cb-example-app-terraform/terraform.tfstate"
    region  = "us-east-1"
    encrypt = true

    skip_metadata_api_check     = true
    skip_region_validation      = true
    skip_credentials_validation = true
  }
}
provider "aws" {
  region = local.region

  skip_get_ec2_platforms      = true
  skip_metadata_api_check     = true
  skip_region_validation      = true
  skip_credentials_validation = true
}

##################################################################
#                       locals
##################################################################

locals {
  region          = "us-east-1"
  resource_prefix = "cb-example-app-terraform"
}

data "aws_caller_identity" "i" {}

data "aws_organizations_organization" "o" {}


resource "aws_sqs_queue" "a" {
  name                        = "${local.resource_prefix}-a.fifo"
  fifo_queue                  = true
  content_based_deduplication = true
}

resource "aws_sqs_queue" "b" {
  name                        = "${local.resource_prefix}-b.fifo"
  fifo_queue                  = true
  # content_based_deduplication = false
  content_based_deduplication = true
}


# terraform plan --out tfplan.binary && terraform show -json tfplan.binary > tfplan.json