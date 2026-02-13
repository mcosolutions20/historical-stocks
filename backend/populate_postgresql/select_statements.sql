-- Retrieve all records from the specified table
-- SELECT * FROM table_name; 
SELECT * FROM sp500_historical;

-- Delete all records from the table and reset identity/auto-incrementing primary key
-- TRUNCATE TABLE table_name RESTART IDENTITY;
TRUNCATE TABLE sp500_historical RESTART IDENTITY;

-- Count the number of records in the specified table
-- SELECT COUNT(*) FROM table_name;
SELECT COUNT(*) FROM sp500_historical;