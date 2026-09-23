-- Runs once, automatically, when the `db` container first initializes its
-- data directory (see docker-entrypoint-initdb.d in the official mysql
-- image docs) — never on a re-used volume.
--
-- The official mysql image only grants MYSQL_USER privileges on
-- MYSQL_DATABASE itself. Django's test runner needs to CREATE/DROP its own
-- `test_<MYSQL_DATABASE>` database on every `manage.py test` run, so
-- without this grant that fails with "Access denied ... to database
-- 'test_coolregistration'". This grants that up front so testing just
-- works, no manual step required.
GRANT ALL PRIVILEGES ON `test_%`.* TO 'coolregistration'@'%';
FLUSH PRIVILEGES;
