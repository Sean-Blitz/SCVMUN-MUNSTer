# SCVMUN-MUNSTer

In-development

An easily deployable, full-stack monolith web application using FastAPI and Vue, designed to serve MUN conferences for position papers
and final grading.

## Features
- **Easy admin interface** powerful and intuitive control over the data.
- **Cross-platform:** works on almost any server deployments using Docker.
- **High maintainability:** detailed documentation, a full testing suite, and simple design by nature.

## Getting Started

Placeholder, in progress.

### Prerequisites

Minimum requirements:
- Docker engine installed
- 2 CPU cores
- 4 GB of RAM
- 16 GB of free storage
- Ports 80 and 443 open

Recommended:
- Linux OS
- Port 22 open on local network / constant physical access
- Nginx reverse proxy installed

### Testing Installation
Placeholder, in progress

1. Clone the repository:
   ```bash
   git clone https://github.com/Sean-Blitz/SCVMUN-MUNSTer.git
   ```
2. Navigate to the Frontend directory:
   ```bash
   cd SCVMUN-MUNSTer/Frontend
   ```
3. Install dependencies:
   ```bash
   npm install
   ```

## Docker Usage

The whole platform runs as three containers — nginx serving the built SPA and terminating
TLS, the FastAPI backend, and PostgreSQL:

```bash
cp .env.example .env          # set POSTGRES_PASSWORD at minimum
# put fullchain.pem and privkey.pem in tls/  (see deploy/TLS.md)
docker compose up -d --build
docker compose run --rm api python crud/seed.py
docker compose run --rm api python -m crud.bootstrap --admin-name "Your Name"
```

`bootstrap.py` prints the admin access code once; claim it with "First-Time Register" on the
login page.

- **Full self-hosting guide:** [`deploy/README.md`](deploy/README.md)
- **Certificate setup, renewal and troubleshooting:** [`deploy/TLS.md`](deploy/TLS.md)

For frontend development without containers:

```bash
cd Frontend
npm install
npm run dev
```

## 🗺️ Roadmap
- [ ] First release and conference use at SCVMUN LVI
- [ ] Additional test suites and migration scripts
- [ ] Server hosting and expansion to other conferences

## 🤝 Contributing
Contributions are welcome! Please follow these steps:
1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 License
Distributed under the MIT License. See `LICENSE.txt` for more information.

## 📬 Contact
Your Name - [@yourusername](https://twitter.com) - email@example.com  
Project Link: [https://github.com](https://github.com)
