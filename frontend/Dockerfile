FROM nginx/nginx-unprivileged:1.30.6-alpine3.24

COPY --chown=nginx:nginx index.html /usr/share/nginx/html/
COPY --chown=nginx:nginx src/ /usr/share/nginx/html/src/
COPY --chown=nginx:nginx docker/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080
