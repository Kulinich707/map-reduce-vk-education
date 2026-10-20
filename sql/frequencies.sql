CREATE OR REPLACE TEMP TABLE population AS
WITH canonical AS (
 SELECT *,row_number() OVER(PARTITION BY id ORDER BY row_no::BIGINT) rn
 FROM read_csv($source,header=true,all_varchar=true)
), selected AS (
 SELECT * FROM canonical WHERE rn=1 AND role='Программист, разработчик'
 AND (regexp_matches(title,'\bphp(?:[578](?:\.[0-9]+)*)?\b','i') OR list_count(list_filter(
   json_extract(skills_json,'$')::VARCHAR[],x->regexp_full_match(lower(trim(x)),'php(?:[578](?:\.[0-9]+)*)?')))>0)
)
SELECT *,list_sort(list_distinct(list_filter(list_transform(
 json_extract(skills_json,'$')::VARCHAR[],x->lower(regexp_replace(trim(x),'\s+',' ','g'))),x->x<>''))) skills,
CASE WHEN upper(coalesce(currency,'')) NOT IN ('RUR','RUB') OR lower(coalesce(gross,''))<>'false' THEN NULL
 WHEN try_cast(salary_from AS DOUBLE)>0 AND try_cast(salary_to AS DOUBLE)>0
   THEN (salary_from::DOUBLE+salary_to::DOUBLE)/2
 WHEN try_cast(salary_from AS DOUBLE)>0 THEN salary_from::DOUBLE
 WHEN try_cast(salary_to AS DOUBLE)>0 THEN salary_to::DOUBLE ELSE NULL END salary
FROM selected;

CREATE OR REPLACE TEMP TABLE skills_long AS
SELECT id,unnest(list_slice(skills,1,$cap)) skill FROM population;

SELECT to_json(list_value(skill))::VARCHAR AS "key",count(*)::BIGINT AS n FROM skills_long GROUP BY skill
UNION ALL
SELECT to_json(list_value(a.skill,b.skill))::VARCHAR,count(*)::BIGINT
FROM skills_long a JOIN skills_long b ON a.id=b.id AND a.skill<b.skill GROUP BY a.skill,b.skill
UNION ALL
SELECT to_json(list_value(a.skill,b.skill,c.skill))::VARCHAR,count(*)::BIGINT
FROM skills_long a JOIN skills_long b ON a.id=b.id AND a.skill<b.skill
JOIN skills_long c ON a.id=c.id AND b.skill<c.skill GROUP BY a.skill,b.skill,c.skill;
