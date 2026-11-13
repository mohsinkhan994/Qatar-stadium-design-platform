FROM nginx/nginx-unprivileged:1.30.6-alpine3.24

COPY --chown=nginx:nginx index.html styles.css app.js /usr/share/nginx/html/
COPY --chown=nginx:nginx nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080
