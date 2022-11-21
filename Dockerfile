FROM alpine AS builder

ENV PYENV_ROOT=/opt/.pyenv

ENV PATH="$PYENV_ROOT/bin:$PATH"
ENV PATH="$PYENV_ROOT/versions/3.11.0/bin:$PATH"
ENV PATH="$PYENV_ROOT/versions/3.10.8/bin:$PATH"
ENV PATH="$PYENV_ROOT/versions/3.9.15/bin:$PATH"
ENV PATH="$PYENV_ROOT/versions/3.8.15/bin:$PATH"

RUN apk add --no-cache bash git \
    && git clone https://github.com/pyenv/pyenv.git $PYENV_ROOT \
    && apk add --no-cache \
        build-base libffi-dev openssl-dev bzip2-dev \
        zlib-dev xz-dev readline-dev sqlite-dev tk-dev \
    && pyenv install 3.8.15 \
    && pyenv install 3.9.15 \
    && pyenv install 3.10.8 \
    && pyenv install 3.11.0 \
    && python3.8 -m pip install ansible pytest pytest-forked \
    && python3.9 -m pip install ansible pytest pytest-forked \
    && python3.10 -m pip install ansible pytest pytest-forked \
    && python3.11 -m pip install ansible pytest pytest-forked

FROM alpine

ENV PYENV_ROOT=/opt/.pyenv

ENV PATH="$PYENV_ROOT/bin:$PATH"
ENV PATH="$PYENV_ROOT/versions/3.11.0/bin:$PATH"
ENV PATH="$PYENV_ROOT/versions/3.10.8/bin:$PATH"
ENV PATH="$PYENV_ROOT/versions/3.9.15/bin:$PATH"
ENV PATH="$PYENV_ROOT/versions/3.8.15/bin:$PATH"

COPY --from=builder $PYENV_ROOT $PYENV_ROOT

RUN apk add --no-cache libffi

ENTRYPOINT [ "ansible-test" ]
