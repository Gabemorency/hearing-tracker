-- Add a photo URL to members, sourced from unitedstates/images (the same
-- CDN the old static-site generator used). Safe to run again.
alter table members add column if not exists photo_url text;
