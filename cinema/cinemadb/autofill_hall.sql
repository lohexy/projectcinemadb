CREATE DEFINER=`root`@`localhost` PROCEDURE `sp_FillHall`(IN hallID INT, IN totalRows INT, IN seatsPerRow INT)
BEGIN
    DECLARE r INT DEFAULT 1;
    DECLARE s INT DEFAULT 1;
    
    WHILE r <= totalRows DO
        SET s = 1;
        WHILE s <= seatsPerRow DO
            
            -- ВИПРАВЛЕНО ТУТ:
            INSERT INTO hall_seats_map (hall_id, `row_number`, seat_number)
            VALUES (hallID, r, s);
            
            SET s = s + 1;
        END WHILE;
        SET r = r + 1;
    END WHILE;
END