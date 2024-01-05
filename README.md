# Weni

[![Build Status](https://github.com/weni-ai/nexus-ai/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Ilhasoft/nexus-ai/actions/workflows/ci.yml?query=branch%3Amain)
[![Coverage Status](https://coveralls.io/repos/github/Ilhasoft/nexus-ai/badge.svg?branch=main)](https://coveralls.io/github/Ilhasoft/nexus-ai?branch=main)
[![Python Version](https://img.shields.io/badge/python-3.10-blue.svg)](https://www.python.org/)
[![License: MPL 2.0](https://img.shields.io/badge/License-MPL_2.0-brightgreen.svg)](https://opensource.org/licenses/MPL-2.0)

## Index

[Running locally](#running)

[Environment Variables List](#environment-variables-list)

[License](#license)

[Contributing](#contributing)

## Running

```sh
git clone https://github.com/weni-ai/nexus-ai.git
```


### Required environment variables

```
DEBUG=
ALLOWED_HOSTS=,
SECRET_KEY=
```

## License

Distributed under the MPL-2.0 License. See `LICENSE` for more information.

## Running

[Install docker](https://docs.docker.com/get-docker/)

Create an .env file in the project root and add the above environment variables

For authentication, we use Keycloak, you need to run it locally:
  - [Documentation](https://www.keycloak.org/documentation.html)

Execute `docker-compose build` to build application

Execute `docker-compose up` to up the server

Very good, your application is running :rocket:                                   


## Contributing

Contributions are what make the open source community such an amazing place to be learn, inspire, and create. Any contributions you make are **greatly appreciated**.

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

To see more go to the [Weni Platform central repository](https://github.com/Ilhasoft/weni-platform).
