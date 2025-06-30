# DataSpace Multi-Service Architecture for AWS ECS

This document outlines the architecture for deploying the DataSpace application and its dependent services to AWS ECS.

## Architecture Overview

The DataSpace application consists of several services that work together:

1. **Backend Application (dataspace)** - The main Django/Python application
2. **PostgreSQL Database (backend_db)** - Database for the application
3. **Elasticsearch** - For search functionality
4. **Redis** - For caching and possibly message queuing
5. **Telemetry Services** - Including OpenTelemetry Collector

## AWS Services Mapping

For production deployment on AWS, we use the following mapping:

| Local Service | AWS Service | Justification |
|---------------|-------------|---------------|
| dataspace (backend) | ECS Fargate | Containerized application, managed by ECS |
| backend_db | Amazon RDS for PostgreSQL | Managed database service with backups, high availability |
| elasticsearch | Amazon Elasticsearch Service | Managed Elasticsearch with scaling and security |
| redis | Amazon ElastiCache for Redis | Managed Redis with high availability |
| otel-collector | ECS Fargate (separate task) | Deployed as a separate container service |

## Deployment Architecture

### Infrastructure as Code

All AWS resources are provisioned using CloudFormation templates located in `aws/cloudformation/`. The main template `dataspace-infrastructure.yml` creates:

1. **Security Groups** - For RDS, Elasticsearch, Redis, and ECS services
2. **Amazon RDS PostgreSQL** - Managed database with subnet group
3. **Amazon Elasticsearch Service** - Managed Elasticsearch domain with security and access policies
4. **Amazon ElastiCache Redis** - Managed Redis cluster
5. **ECS Cluster** - With Fargate and Fargate Spot capacity providers
6. **IAM Roles** - For ECS task execution with appropriate permissions
7. **SSM Parameters** - For storing sensitive connection information

### ECS Task Definitions

The application is deployed using two main ECS task definitions:

1. **Main Application (`aws/task-definition.json`)** - Deploys the Django application container with:
   - Environment variables for configuration
   - Secrets from SSM Parameter Store for sensitive data
   - Health checks and logging configuration
   - Network configuration for service discovery

2. **OpenTelemetry Collector (`aws/otel-collector-task-definition.json`)** - Deploys the telemetry collector with:
   - Port mappings for various telemetry protocols
   - Volume mounts for configuration
   - Health checks and logging

### Managed Services Integration

#### Amazon RDS PostgreSQL

The PostgreSQL database is provisioned as a managed RDS instance with:

- Automated backups
- Security group restrictions (only accessible from ECS tasks)
- Credentials stored in SSM Parameter Store
- Connection information injected into the application container as environment variables

#### Amazon Elasticsearch Service

Elasticsearch is provisioned as a managed service with:

- Fine-grained access control
- HTTPS encryption
- Security group restrictions
- Connection information stored in SSM Parameter Store

#### Amazon ElastiCache Redis

Redis is provisioned as a managed ElastiCache cluster with:

- Security group restrictions
- Connection information stored in SSM Parameter Store
- Host and port injected into the application container

## CI/CD Pipeline

The deployment is automated using GitHub Actions workflow (`.github/workflows/deploy-to-ecs.yml`) that:

1. **Triggers** on pushes to the `dev` branch or manual workflow dispatch
2. **Deploys Infrastructure** using CloudFormation (conditionally based on changes)
3. **Builds and Pushes** Docker images to Amazon ECR
4. **Deploys Application** using ECS task definitions with environment variable substitution
5. **Deploys OpenTelemetry Collector** as a separate ECS service

### Idempotent Infrastructure Creation

The CloudFormation template is designed to be idempotent by:

1. Using the `--no-fail-on-empty-changeset` flag in CloudFormation deployment
2. Setting appropriate `DeletionPolicy` and `UpdateReplacePolicy` attributes on resources
3. Using conditional resource creation based on environment parameters

This ensures that:
- If resources already exist, they won't be recreated unnecessarily
- Database and Elasticsearch data is preserved during updates
- Application code can be updated independently of infrastructure

## Environment Variables and Secrets Management

The deployment uses a three-tier approach to configuration:

1. **GitHub Repository Secrets** - For AWS credentials and sensitive parameters
2. **Environment Variables** - For non-sensitive configuration in CI/CD and ECS tasks
3. **AWS SSM Parameter Store** - For service connection information and secrets

### Required GitHub Secrets

- `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` - AWS credentials
- `AWS_REGION` - Target AWS region
- `ECR_REPOSITORY` - ECR repository name
- `ECS_CLUSTER` - ECS cluster name
- `ECS_SERVICE` - Main application ECS service name
- `ECS_OTEL_SERVICE` - OpenTelemetry collector ECS service name
- `ECS_EXECUTION_ROLE_ARN` - ECS task execution role ARN
- `VPC_ID` and `SUBNET_IDS` - VPC and subnet IDs
- `DB_USERNAME`, `DB_PASSWORD`, `DB_NAME` - Database credentials
- `ELASTICSEARCH_PASSWORD` - Elasticsearch password
- `DJANGO_SECRET_KEY` - Django secret key
- `ENVIRONMENT` - Deployment environment (dev, staging, prod)

## Scaling and High Availability

The architecture supports scaling and high availability through:

1. **ECS Fargate** - Automatic scaling based on CPU/memory usage
2. **RDS Multi-AZ** - Optional database high availability
3. **ElastiCache Replication** - Optional Redis replication
4. **Elasticsearch Multi-Node** - Optional Elasticsearch cluster scaling

## Monitoring and Observability

The deployment includes observability through:

1. **CloudWatch Logs** - For all ECS services
2. **OpenTelemetry Collector** - For metrics, traces, and logs collection
3. **Health Checks** - For all services to ensure availability

## Security Considerations

The deployment implements security best practices:

1. **IAM Least Privilege** - Task execution role with minimal permissions
2. **Security Groups** - Restrict access between services
3. **Secrets Management** - Sensitive data in SSM Parameter Store
4. **Network Isolation** - Services in private subnets where appropriate
5. **HTTPS** - For all external communication

This approach uses AWS managed services where possible and ECS only for custom application containers:

- **Backend Application**: ECS Fargate Task/Service
- **Database**: Amazon RDS
- **Elasticsearch**: Amazon Elasticsearch Service
- **Redis**: Amazon ElastiCache
- **Telemetry**: Amazon Elasticsearch Service + ECS for collectors/agents

### Option 2: ECS for Everything

This approach deploys everything as containers in ECS:

- **Backend Application**: ECS Fargate Task/Service
- **Database**: ECS Fargate Task with PostgreSQL container + EBS volume
- **Elasticsearch**: ECS Fargate Task with Elasticsearch container + EBS volume
- **Redis**: ECS Fargate Task with Redis container
- **Telemetry**: ECS Fargate Tasks for all telemetry services

### Recommended Approach

We recommend **Option 1** for production workloads because:

1. Managed services handle backups, high availability, and security patches
2. Reduced operational overhead
3. Better scalability and reliability
4. Separation of concerns

## Implementation Plan

### 1. Create AWS Managed Services

First, create the necessary managed services:

- **RDS PostgreSQL Instance**
- **ElastiCache Redis Cluster**
- **Amazon Elasticsearch Service Domain(s)**

### 2. Update Task Definition for Backend Application

The task definition we've already created focuses on the backend application. It needs to be updated with connection information for the managed services.

### 3. Create Task Definitions for Custom Services

For services that don't have AWS managed equivalents (like otel-collector), create separate task definitions.

### 4. Update CI/CD Pipeline

Update the GitHub Actions workflow to:

1. Deploy infrastructure changes if needed (using Terraform or CloudFormation)
2. Deploy application containers to ECS

## Example: RDS Configuration

```bash
# Create RDS instance
aws rds create-db-instance \
  --db-instance-identifier dataspace-db \
  --db-instance-class db.t3.small \
  --engine postgres \
  --master-username ${DB_USERNAME} \
  --master-user-password ${DB_PASSWORD} \
  --allocated-storage 20
```

## Example: ElastiCache Configuration

```bash
# Create ElastiCache cluster
aws elasticache create-cache-cluster \
  --cache-cluster-id dataspace-redis \
  --engine redis \
  --cache-node-type cache.t3.small \
  --num-cache-nodes 1
```

## Example: Amazon Elasticsearch Service

```bash
# Create Elasticsearch domain
aws es create-elasticsearch-domain \
  --domain-name dataspace-search \
  --elasticsearch-version 7.10 \
  --elasticsearch-cluster-config InstanceType=t3.small.elasticsearch,InstanceCount=1 \
  --ebs-options EBSEnabled=true,VolumeType=gp2,VolumeSize=10
```

## Next Steps

1. Create CloudFormation or Terraform templates for the infrastructure
2. Update the ECS task definition with connection information for managed services
3. Create separate task definitions for services that need to run in ECS
4. Update the CI/CD pipeline to deploy all components
