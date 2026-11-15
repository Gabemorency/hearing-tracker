-- Congressional district and state outline shapes, sourced from Census
-- cartographic boundary files (1:500,000, generalized for small reference
-- maps). Partitioned by `congress` so a new Congress's boundaries land as
-- new rows rather than overwriting history — nothing here ever needs to
-- be deleted after a redistricting cycle.
create table if not exists district_shapes (
  id          bigint generated always as identity primary key,
  congress    int not null,
  state       text not null,
  district    text not null default '',  -- '' = whole-state outline (for Senators); otherwise '0' (at-large) or a district number
  geometry    jsonb not null,            -- GeoJSON Polygon or MultiPolygon
  fetched_at  timestamptz not null default now(),
  unique (congress, state, district)
);
create index if not exists district_shapes_state_idx on district_shapes (state);

alter table district_shapes enable row level security;
drop policy if exists "public read" on district_shapes;
create policy "public read" on district_shapes for select using (true);
