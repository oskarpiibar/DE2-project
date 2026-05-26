<p align="center">
    <h1 align="center">Github Starts Predictor</h1>
</p>
<p align="center">
    <em>A Scalable Machine Learning System for Predicting Github Repository Popularity</em>
</p>

<!-- TABLE OF CONTENTS -->
<details>
  <summary>Table of Contents</summary>

- [📍 Overview](#-overview)
- [🗂️ Repository Structure](#-repository-structure)
- [📦 Modules](#-modules)
- [🚀 How to Run](#-how-to-run)
  - [⚙️ Prerequisites](#️-prereqisite)
  - [🤖 Deploy](#-deploy)
  - [🧪 Test](#-test)
- [📄 License](#-license)
- [👏 Acknowledgments](#-acknowledgments)
</details>
<hr>

## 📍 Overview

This project goes beyond building a machine learning model to predict the star count of GitHub repositories, it demonstrates an MLOps ecosystem designed for scalability, automation, and operational reliability.

The system is built around an end-to-end architecture that spans both development and production environments. In the development environment, the pipeline supports data collection, preprocessing, experimentation, and distributed model training. Once trained, models can be automatically deployed into production through a CI/CD workflow powered by Git hooks, reducing manual intervention and enabling faster iteration cycles.

On the production side, the system serves predictions through scalable back-end and front-end services deployed behind a load balancer, allowing requests to be efficiently distributed across instances. Scalability is a core design principle: distributed training with Ray and prediction services built with FastAPI are architected for horizontal expansion and performance testing under increasing workloads.

![System Architecture](figures/system_architecture.png)

Key highlights:

- 🤖 Machine learning model for GitHub repository star prediction
- ⚙️ End-to-end MLOps workflow from training to deployment
- 📈 Horizontally scalable training and inference services
- 🔄 Automated CI/CD for model deployment using Git hooks
- 🌐 Load-balanced production architecture
- 🔐 Secure infrastructure with bastion host access control


## 🗂️ Repository Structure

```sh
└── /
    ├── ansible/    # ansible sript for orchestration
    ├── data/       # raw and clean dataset
    ├── models/     # best ML model (.pkl) and its metadata
    ├── notebooks/  # exporation python notebooks
    ├── script/
    │   ├── install/    # installation script
    │   └── ray/        # script to test ray cluster
    ├── src
    │   ├── app         # frontend+backend of predictor app
    │   ├── data        # data collector script
    │   ├── features    # pre-processing and feature engineering script
    │   ├── tests       # scalability test script (locust)
    │   └── training    # model training script
    └── terraform       # terraform script for spawning infrastructure
```

## 🚀 How to run

This project designed to run on distributed cloud environment (multi VM), in this case OpenStack. Minimum 3 VMs are required, 1 for jump-server, 1 for development server, and 1 for production server.

### Prerequisite 

Ansible, Terraform, OpenStack Client intalled (on jump server). Provided installation script at `script/install/` directory.

### Deploy

1. Spawn infrastructure using Terraform. Read more at [`terraform/`](./terraform/) directory
2. Contextualize and orchestrate infrastructure using Ansible. Read more at [`ansible/`](./ansible/) directory
3. The gateway located at `prod1` host. Get its public IP and access predictor app through port `8888`

### Test

(Optional) If you want to test the predictor app's inference performance, read more at [`src/tests`](./src/tests/)


## 👏 Acknowledgments

### Contributors: