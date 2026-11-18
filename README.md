# SCVMUN-MUNSTer

**Status: Internal Alpha Testing**

An easily deployable, full-stack monolith web application using FastAPI and Vue, designed to serve MUN conferences for position papers
and final grading.

## Features
- **Easy admin interface:** powerful and intuitive control over the data.
- **Cross-platform:** works on almost any server deployments using Docker.
- **High maintainability:** detailed documentation, a full testing suite, and simple design by nature.

## Getting Started

For regular/non-technical end users, this project can be deployed onto a server computer easily using Docker containers. These are essentially "mini operating systems" that run on the computer. There are three of them:
   - **Nginx:** a container that serves the website UI (Frontend) and handles public web traffic to your computer.
   - **API:** the container which handles logic and connects the Frontend with permanent data storage.
   - **Postgres:** a data storage container which has all your conference information from the current session.
See below and other files referenced in this document for further instructions. Any questions should be directed to the contact listed below.

For more technical users, MUNSTer is designed using Javascript's Vue, Python's FastAPI + SQLAlchemy, and PostgreSQL. 

### Prerequisites

**Minimum requirements** for local build:
- Docker engine installed
- 2 CPU cores
- 4 GB of RAM
- 16 GB of free storage
- Ports 80 and 443 open

**Recommended** for production:
- Linux OS
- Port 22 open on local network / constant physical access
- An SSL certificate and domain name
- DNS entry for your domain name + static IP (or another method of public access)

### Testing Installation
For local builds, not deployment.

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
4. Navigate to the Backend directory:
   ```bash
   cd ../Backend
   ```
5. Create a venv and install dependencies:
   ```bash
   python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
   ```
6. Point the API at a database: copy `crud/.env.example` to `crud/.env` and set `DATABASE_URL` to a running PostgreSQL. Without it uvicorn exits with "DATABASE_URL is not set".


7. Point Frontend to the local running backend: copy `Frontend/.env.example` to `Frontend/.env`and set `VITE_API_BASE_URL=http://localhost:8000/api`.
8. Run the uvicorn app:
   ```bash
   uvicorn main:app --reload
   ```

Now start the frontend dev server in a second terminal (`cd Frontend && npm run dev`) and open the link Vite prints to test the website!

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

## Roadmap
- [ ] First release and conference use at SCVMUN LVI
- [ ] Additional test suites and migration scripts
- [ ] Server hosting and expansion to other conferences

## Contributing
Contributions are welcome! Please follow these steps:
1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License
Distributed under the MIT License. See `LICENSE.txt` for more information.

Note: the folder Frontend/src/components/soap-bubble is not covered by this MIT license and is not owned by the repository owners. See files for its own specific ReactDrops Component License 1.0.

## Contact
This project is maintained by the Santa Teresa High School Model United Nations tech team. We are a small group of part-time student developers. If you have any questions, we will try to respond as soon as possible, but please be aware of our student schedules.


Siyan Mu - Project Lead - sg@scvmun.com
