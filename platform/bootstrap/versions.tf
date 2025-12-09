terraform {
  required_version = "= 1.10.5"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "= 4.27.0"
    }
  }
}

provider "azurerm" {
  features {}
  resource_provider_registrations = "none"
}
