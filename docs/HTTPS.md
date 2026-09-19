# HTTPS и проверка с телефона

Локальная версия работает на `http://localhost`. Браузеры считают localhost безопасным контекстом, но телефон понимает localhost как адрес **самого телефона**, а не компьютера преподавателя. Обычный адрес вида `http://192.168.x.x` не обеспечивает безопасный контекст для геолокации. См. [Geolocation API](https://developer.mozilla.org/en-US/docs/Web/API/Geolocation_API) и [Secure contexts](https://developer.mozilla.org/en-US/docs/Web/Security/Secure_Contexts).

Ниже — инструкция для самостоятельной настройки владельцем установки. При разработке внешние серверы, DNS и SSL-сертификаты не создавались. Используйте свой домен: `qr.example.org` здесь только пример; домены старого проекта не предполагают наличие у вас прав управления ими.

## Вариант с собственным доменом и сервером

Команды рассчитаны на bash/zsh на сервере с Docker Compose. Для доступа через домашний компьютер дополнительно потребуется доступность его портов из интернета; за CGNAT обычно удобнее сервер с публичным IP. Не требуется открывать порты PostgreSQL и FastAPI.

1. Разместите репозиторий на своём сервере. Настройте DNS A-запись `qr.example.org` на его публичный IPv4. Если настроена AAAA-запись, IPv6 также должен вести на этот сервер. Разрешите входящие TCP 80 и 443.
2. Скопируйте `.env.example` в `.env`. До первой инициализации БД задайте длинный случайный буквенно-цифровой `POSTGRES_PASSWORD`. Для сайта установите:

   ```dotenv
   PUBLIC_BASE_URL=https://qr.example.org
   HTTP_PORT=80
   COOKIE_SECURE=true
   ```

   `APP_SECRET` можно оставить пустым: приложение сохранит случайный секрет в томе `app_data`. Не удаляйте этот том при обновлении.

3. Получите сертификат. Для standalone-проверки Certbot требуется свободный порт 80. Остановите контейнер Nginx и выполните команды из корня проекта:

   ```bash
   docker compose stop nginx
   mkdir -p .certificates
   docker run --rm -it -p 80:80 \
     -v "$PWD/.certificates:/etc/letsencrypt" \
     certbot/certbot certonly --standalone -d qr.example.org
   ```

   Certbot предложит ввести email и ознакомиться с условиями. Выполняет и подтверждает эти действия владелец домена. Каталог `.certificates` исключён из Git и Docker build context. Метод описан в [официальной документации Certbot](https://eff-certbot.readthedocs.io/en/stable/using.html#standalone).

4. Создайте конфигурацию HTTPS:

   ```bash
   cp nginx/https.conf.example nginx/https.conf
   ```

   Откройте `nginx/https.conf` и замените **все** `YOUR_DOMAIN` на `qr.example.org`. Указанные пути `live/qr.example.org/fullchain.pem` и `privkey.pem` должны существовать внутри `.certificates`. Используется полная цепочка сертификата. См. [настройку HTTPS в Nginx](https://nginx.org/en/docs/http/configuring_https_servers.html).

5. Запустите с дополнительной конфигурацией:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.https.yml up --build -d --wait
   docker compose -f docker-compose.yml -f docker-compose.https.yml exec nginx nginx -t
   ```

   Основной порт 80 сохранится для редиректа, добавится 443. Точка `/health` доступна по HTTP для healthcheck, остальные HTTP-страницы перенаправляются на ваш HTTPS-домен. Конфигурация HTTPS использует TLS 1.2/1.3.

6. Откройте `https://qr.example.org` на компьютере. Создайте **новую** сессию в браузере на этом домене. Старые cookie localhost к домену не относятся.
7. Сканируйте QR телефоном. Проверьте, что браузер не показывает ошибок сертификата, разрешите геолокацию и отправьте тестовую отметку. Проверьте журнал и Excel на компьютере.

После перехода на HTTPS все команды обновления выполняйте с **обоими** `-f`. Запуск только базового файла вернёт HTTP-конфигурацию.

## Продление сертификата

Сертификаты нужно своевременно продлевать. Для выбранного standalone-метода требуется короткая остановка Nginx. Владелец сервера может запускать эти команды вручную или настроить собственное расписание:

```bash
docker compose -f docker-compose.yml -f docker-compose.https.yml stop nginx
docker run --rm -p 80:80 \
  -v "$PWD/.certificates:/etc/letsencrypt" \
  certbot/certbot renew
docker compose -f docker-compose.yml -f docker-compose.https.yml start nginx
```

Проверяйте результат Certbot. После остановки Nginx верните его в работу даже при ошибке продления. Для предварительной проверки можно использовать `renew --dry-run`. В этом проекте автоматическое расписание продления не устанавливается. См. [renewal в Certbot](https://eff-certbot.readthedocs.io/en/stable/using.html#renewing-certificates).

## Что проверить, если телефон не отмечается

- QR содержит правильный HTTPS-домен и доступен из сети телефона.
- Сертификат действителен для домена и доверен телефону.
- Доступ к геолокации разрешён и в браузере, и в ОС.
- Координаты центра и радиус заданы правильно; GPS внутри помещения может давать значительную погрешность.
- `PUBLIC_BASE_URL` совпадает с адресом страницы, `COOKIE_SECURE=true`.
- Браузер не потерял cookie; время сессии ещё не истекло.

Если геолокация не работает, преподаватель может подтвердить присутствие и добавить студента вручную. Это предусмотренный сценарий исходного проекта.
