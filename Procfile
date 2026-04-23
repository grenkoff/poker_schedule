web: gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 3 --access-logfile -
release: python manage.py migrate --noinput && python manage.py compilemessages --ignore=.venv && python manage.py collectstatic --noinput
