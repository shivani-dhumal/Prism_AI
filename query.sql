SELECT * FROM codebase_scanner_db.ui_consistency_report;

SELECT *
FROM ui_consistency_report
WHERE status = 'FAIL';

SELECT *
FROM ui_consistency_report
WHERE screen_name = 'Home.vue';

SELECT COUNT(*) AS total_failures
FROM ui_consistency_report
WHERE status = 'FAIL';