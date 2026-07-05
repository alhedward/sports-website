terraform {
  backend "s3" {
    bucket         = "lroc-terraform-state-191831370230"
    key            = "lroc/site/terraform.tfstate"
    region         = "ap-southeast-2"
    dynamodb_table = "lroc-terraform-locks-191831370230"
    encrypt        = true
  }
}
