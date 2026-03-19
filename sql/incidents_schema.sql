-- Run this against your Target Azure SQL Database.
-- The incidents table stores all self-healing state as JSON blobs,
-- replacing the Cosmos DB container.

CREATE TABLE incidents (
    id          NVARCHAR(100)  NOT NULL PRIMARY KEY,
    data        NVARCHAR(MAX)  NOT NULL,          -- full incident JSON
    created_at  DATETIME2      NOT NULL DEFAULT GETUTCDATE()
);

-- Optional index for fast time-ordered listing
CREATE INDEX ix_incidents_created_at ON incidents (created_at DESC);
