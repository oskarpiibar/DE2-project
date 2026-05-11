#!/bin/bash

# Script to deploy dev and prod environments using Terraform
# Usage: ./deploy_prod_n_dev.sh [dev|prod|all]
# Default: all

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to deploy a specific environment
deploy_environment() {
    local env=$1
    local env_path="environments/$env"

    if [ ! -d "$env_path" ]; then
        print_error "Environment directory $env_path does not exist"
        return 1
    fi

    print_status "Deploying $env environment..."

    cd "$env_path"

    # Initialize Terraform if not already done
    if [ ! -d ".terraform" ]; then
        print_status "Initializing Terraform for $env..."
        terraform init
    fi

    # Validate configuration
    print_status "Validating Terraform configuration for $env..."
    terraform validate

    # Plan the deployment
    print_status "Planning deployment for $env..."
    terraform plan -out=tfplan

    # Apply the deployment
    print_status "Applying deployment for $env..."
    terraform apply tfplan

    # Clean up plan file
    rm -f tfplan

    print_status "$env environment deployed successfully!"

    cd - > /dev/null
}

# Main script
ENVIRONMENT=${1:-all}

case $ENVIRONMENT in
    dev)
        deploy_environment "dev"
        ;;
    prod)
        deploy_environment "prod"
        ;;
    all)
        deploy_environment "dev"
        echo ""
        deploy_environment "prod"
        ;;
    *)
        print_error "Invalid environment: $ENVIRONMENT"
        echo "Usage: $0 [dev|prod|all]"
        exit 1
        ;;
esac

print_status "Deployment completed successfully!"