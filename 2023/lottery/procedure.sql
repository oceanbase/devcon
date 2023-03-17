DROP PROCEDURE IF EXISTS draw;

delimiter //
create procedure draw(prize_name varchar(200), draw_count bigint)
begin
  # 参数校验
  if (draw_count <= 0) then
    select CONCAT("Invalid Argument. draw_count is invalid: ", CONVERT(draw_count, CHAR)) as ERROR;
  else
    # 验证奖品
    select count(1) into @prize_item_count from prize where prize.name = prize_name;
    if (@prize_item_count != 1) then
      select CONCAT("No such prize or more than 1: ", prize_name, '. Prize number is ', CONVERT(@prize_item_count, CHAR)) as ERROR;
    else
      # 确认剩余充足的奖品
      select count into @prize_total_count from prize where prize.name = prize_name;
      select count(1) into @drawed_count from candidate where candidate.prize_id = (select id from prize where prize.name = prize_name);
      if (@drawed_count + draw_count) > @prize_total_count then
        select CONCAT("Prize is not enough. There are ", CONVERT(@prize_total_count - @drawed_count, CHAR), " left, but you want ", CONVERT(draw_count, CHAR)) AS ERROR;
      else
        # 抽奖
        select id into @prize_id from prize where prize.name=prize_name;

        # 临时表用来记录之前抽中的同学
        drop table if exists lucky_pups;
        create temporary table lucky_pups select name from candidate where candidate.prize_id = @prize_id;
         
        UPDATE candidate set prize_id=@prize_id where prize_id is null order by rand() limit draw_count;

        # 展示本次抽中的同学
        select name '获奖姓名' from candidate where prize_id=@prize_id and name not in (select name from lucky_pups);

        drop table if exists lucky_pups;
      end if;
    end if;
  end if;
end//

delimiter ;

DROP PROCEDURE IF EXISTS list_all_lucky_pups;

delimiter //

# 展示所有中奖的同学
create procedure list_all_lucky_pups()
begin
  select candidate.name as name, prize.type as type, prize.name as prize from candidate, prize 
      where candidate.prize_id=prize.id order by prize.level, prize.name, candidate.name asc;
end //

delimiter ;

# 创建抽奖模拟候选人
DROP PROCEDURE IF EXISTS create_demo_candidate;
delimiter //
create procedure create_demo_candidate(num bigint)
begin
  select 0 into @i;
  while @i < num do
    set @i = @i+1;
    insert into candidate(name) values(CONCAT('abc', CONVERT(@i, CHAR)));
  end while ;
end //

delimiter ;
