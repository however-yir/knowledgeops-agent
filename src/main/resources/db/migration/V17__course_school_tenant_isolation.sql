-- Close cross-tenant data leak on the public school/course/course_reservation
-- tables. The V1 schema did not include a tenant_id column, so
-- agent-driven queries (CourseTools.queryCourse / querySchool /
-- addCourseReservation) could return or insert rows for any tenant.
--
-- The migration adds a NOT NULL tenant_id column to each table with
-- DEFAULT 'public' so existing rows are claimed by the public tenant
-- (consistent with the V6 / V9 tenant isolation migrations), then adds
-- the corresponding tenant-leading indexes.

ALTER TABLE course
  ADD COLUMN tenant_id VARCHAR(64) NOT NULL DEFAULT 'public';

CREATE INDEX idx_course_tenant_id
  ON course (tenant_id, id);

ALTER TABLE school
  ADD COLUMN tenant_id VARCHAR(64) NOT NULL DEFAULT 'public';

CREATE INDEX idx_school_tenant_id
  ON school (tenant_id, id);

ALTER TABLE course_reservation
  ADD COLUMN tenant_id VARCHAR(64) NOT NULL DEFAULT 'public';

CREATE INDEX idx_course_reservation_tenant_id
  ON course_reservation (tenant_id, id);

-- Drop the old school-only city index so the new tenant-leading index can
-- take its place as the dominant lookup path. (city is still indexed via
-- idx_school_tenant_id when queries filter by tenant first.)
-- (no-op if the old index does not exist)
ALTER TABLE school DROP INDEX city;
