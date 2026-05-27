FROM nginx:alpine
COPY index.html /usr/share/nginx/html/index.html
RUN printf 'server { listen %s; root /usr/share/nginx/html; index index.html; \
location / { try_files $uri $uri/ /index.html; } }\n' '$PORT' \
    > /etc/nginx/templates/default.conf.template
EXPOSE 8080
ENV PORT=8080
