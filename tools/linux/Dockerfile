# Builds Cathode's Linux AppImage (tools/build_linux.py). From the repo root:
#   docker build -t cathode-linux-build tools/linux
#   docker run --rm -v "$PWD:/src" -v "<builds dir>:/builds" cathode-linux-build
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-venv python3-dev binutils file wget ca-certificates libmpv2 \
    && rm -rf /var/lib/apt/lists/*
RUN wget -q -O /usr/local/bin/appimagetool \
        https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage \
    && chmod +x /usr/local/bin/appimagetool \
    && wget -q -O /opt/excludelist \
        https://raw.githubusercontent.com/AppImageCommunity/pkg2appimage/master/excludelist
RUN python3 -m venv /venv
# Work inside the container: a Windows bind mount is slow and drops symlinks.
ENV PATH=/venv/bin:$PATH CATHODE_BUILDS=/builds CATHODE_WORK=/work
WORKDIR /src
CMD ["sh", "-c", "pip install -q -r requirements.txt pyinstaller && python tools/build_linux.py"]
