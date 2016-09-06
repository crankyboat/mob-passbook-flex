# Generated with
# gcloud beta app gen-config --custom
FROM gcr.io/google_appengine/python
RUN virtualenv /env -p python2.7

# Set virtualenv environment variables. This is equivalent to running
# source /env/bin/activate
ENV VIRTUAL_ENV /env
ENV PATH /env/bin:$PATH
ADD requirements.txt /app/

# Insert to compile and install cryptography with custom openssl version 
RUN apt-get update && apt-get install -y curl
RUN curl https://www.openssl.org/source/openssl-1.0.2h.tar.gz | tar -xz
WORKDIR openssl-1.0.2h
RUN ./config no-shared no-ssl2 -fPIC --prefix=/home/vmagent/app/openssl
RUN make && make install
WORKDIR ../
RUN CFLAGS="-I/home/vmagent/app/openssl/include" \
    LDFLAGS="-L/home/vmagent/app/openssl/lib" \
    pip wheel --no-use-wheel cryptography 
RUN pip install *.whl && pip install -r requirements.txt

# Resume gcloud generated
ADD . /app/
CMD honcho start -f procfile app