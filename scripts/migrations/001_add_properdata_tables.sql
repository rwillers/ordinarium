BEGIN;

CREATE TABLE IF NOT EXISTS holidays (
  id INTEGER PRIMARY KEY,
  handle TEXT,
  date_rule TEXT,
  style TEXT,
  priority INTEGER,
  colour TEXT,
  propers TEXT,
  name TEXT,
  alternative_name TEXT,
  importable_fragments TEXT
);
CREATE INDEX IF NOT EXISTS idx_holidays_handle ON holidays(handle);
CREATE INDEX IF NOT EXISTS idx_holidays_priority ON holidays(priority);

CREATE TABLE IF NOT EXISTS fragments (
  id INTEGER PRIMARY KEY,
  date_rule TEXT,
  behaviour TEXT,
  propers TEXT
);
CREATE INDEX IF NOT EXISTS idx_fragments_date_rule ON fragments(date_rule);

CREATE TABLE IF NOT EXISTS subcycles (
  id INTEGER PRIMARY KEY,
  handle TEXT,
  epoch INTEGER,
  order_value INTEGER,
  full_cycle INTEGER
);
CREATE INDEX IF NOT EXISTS idx_subcycles_handle ON subcycles(handle);
CREATE INDEX IF NOT EXISTS idx_subcycles_order_value ON subcycles(order_value);

INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (1, 'AdventI', '11/27→Sun', 'Sunday', 2, 'Purple', 'AdventI', 'The First Sunday in Advent', 'Advent Sunday', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (2, 'AdventII', '12/4→Sun', 'Sunday', 2, 'Purple', 'AdventII', 'The Second Sunday in Advent', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (3, 'AdventIII', '12/11→Sun', 'Sunday', 2, 'Rose', 'AdventIII', 'The Third Sunday in Advent', 'Gaudete Sunday', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (4, 'AdventIV', '12/18→Sun', 'Sunday', 2, 'Purple', 'AdventIV', 'The Fourth Sunday in Advent', 'Annunciation Sunday', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (5, 'ChristmasEve', '12/24', 'SeasonDay', 7, 'White', 'ChristmasEve', 'Christmas Eve', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (6, 'Christmas', '12/25', 'Principal', 0, 'White', 'Christmas', 'The Nativity of Our Lord Jesus Christ', 'Christmas Day', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (7, 'ChristmasI', '12/25→Sun (not on 12/25)', 'Sunday', 5, 'White', 'ChristmasI', 'The First Sunday of Christmas', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (8, 'ChristmasII', '1/1→Sun (before 1/6)', 'Sunday', 5, 'White', 'ChristmasII', 'The Second Sunday of Christmas', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (9, 'Epiphany', '1/6', 'Principal', 0, 'White', 'Epiphany', 'The Epiphany of Our Lord Jesus Christ', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (10, 'EpiphanyI', '1/7→Sun', 'Sunday', 5, 'Green', 'EpiphanyI', 'The First Sunday of Epiphany', 'The Baptism of Our Lord Jesus Christ', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (11, 'EpiphanyII', '1/14→Sun', 'Sunday', 5, 'Green', 'EpiphanyII', 'The Second Sunday of Epiphany', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (12, 'EpiphanyIII', '1/21→Sun', 'Sunday', 5, 'Green', 'EpiphanyIII', 'The Third Sunday of Epiphany', '_', 'EpiphanySunday');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (13, 'EpiphanyIV', '1/28→Sun (before E-49)', 'Sunday', 5, 'Green', 'EpiphanyIV', 'The Fourth Sunday of Epiphany', '_', 'EpiphanySunday');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (14, 'EpiphanyV', '2/4→Sun (before E-49)', 'Sunday', 5, 'Green', 'EpiphanyV', 'The Fifth Sunday of Epiphany', '_', 'EpiphanySunday');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (15, 'EpiphanyVI', '2/11→Sun (before E-49)', 'Sunday', 5, 'Green', 'EpiphanyVI', 'The Sixth Sunday of Epiphany', '_', 'EpiphanySunday');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (16, 'EpiphanyVII', '2/18→Sun (before E-49)', 'Sunday', 5, 'Green', 'EpiphanyVII', 'The Seventh Sunday of Epiphany', '_', 'EpiphanySunday');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (17, 'EpiphanyVIII', '2/25→Sun (before E-49)', 'Sunday', 5, 'Green', 'EpiphanyVIII', 'The Eighth Sunday of Epiphany', '_', 'EpiphanySunday');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (18, 'EpiphanyUltima', 'E-49', 'Sunday', 5, 'Green', 'EpiphanyUltima', 'The Last Sunday of Epiphany', 'Transfiguration Sunday', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (19, 'AshWednesday', 'E-46', 'Major', 3, 'Purple', 'AshWednesday', 'Ash Wednesday', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (20, 'LentI', 'E-42', 'Sunday', 2, 'Purple', 'LentI', 'The First Sunday in Lent', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (21, 'LentII', 'E-35', 'Sunday', 2, 'Purple', 'LentII', 'The Second Sunday in Lent', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (22, 'LentIII', 'E-28', 'Sunday', 2, 'Purple', 'LentIII', 'The Third Sunday in Lent', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (23, 'LentIV', 'E-21', 'Sunday', 2, 'Rose', 'LentIV', 'The Fourth Sunday in Lent', 'Laetare Sunday', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (24, 'LentV', 'E-14', 'Sunday', 2, 'Purple', 'LentV', 'The Fifth Sunday in Lent', 'Passion Sunday', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (25, 'PalmSunday', 'E-7', 'Sunday', 2, 'Red', 'PalmSunday', 'Palm Sunday', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (26, 'HolyMonday', 'E-6', 'SeasonDay', 3, 'Red', 'HolyMonday', 'Monday of Holy Week', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (27, 'HolyTuesday', 'E-5', 'SeasonDay', 3, 'Red', 'HolyTuesday', 'Tuesday of Holy Week', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (28, 'HolyWednesday', 'E-4', 'SeasonDay', 3, 'Red', 'HolyWednesday', 'Wednesday of Holy Week', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (29, 'MaundyThursday', 'E-3', 'Major', 3, 'White', 'MaundyThursday', 'Maundy Thursday', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (30, 'GoodFriday', 'E-2', 'Major', 3, 'Red', 'GoodFriday', 'Good Friday', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (31, 'HolySaturday', 'E-1', 'SeasonDay', 3, 'Red', 'HolySaturday', 'Holy Saturday', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (32, 'EasterEve', 'E-1', 'SeasonDay', 7, 'White', 'EasterEve', 'Easter Eve', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (33, 'Easter', 'E', 'Principal', 0, 'White', 'Easter', 'Easter Day', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (34, 'EasterMonday', 'E+1', 'SeasonDay', 3, 'White', 'EasterMonday', 'Monday of Easter Week', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (35, 'EasterTuesday', 'E+2', 'SeasonDay', 3, 'White', 'EasterTuesday', 'Tuesday of Easter Week', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (36, 'EasterWednesday', 'E+3', 'SeasonDay', 3, 'White', 'EasterWednesday', 'Wednesday of Easter Week', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (37, 'EasterThursday', 'E+4', 'SeasonDay', 3, 'White', 'EasterThursday', 'Thursday of Easter Week', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (38, 'EasterFriday', 'E+5', 'SeasonDay', 3, 'White', 'EasterFriday', 'Friday of Easter Week', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (39, 'EasterSaturday', 'E+6', 'SeasonDay', 3, 'White', 'EasterSaturday', 'Saturday of Easter Week', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (40, 'EasterII', 'E+7', 'Sunday', 2, 'White', 'EasterII', 'The Second Sunday of Easter', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (41, 'EasterIII', 'E+14', 'Sunday', 2, 'White', 'EasterIII', 'The Third Sunday of Easter', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (42, 'EasterIV', 'E+21', 'Sunday', 2, 'White', 'EasterIV', 'The Fourth Sunday of Easter', 'Good Shepherd Sunday', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (43, 'EasterV', 'E+28', 'Sunday', 2, 'White', 'EasterV', 'The Fifth Sunday of Easter', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (44, 'EasterVI', 'E+35', 'Sunday', 2, 'White', 'EasterVI', 'The Sixth Sunday of Easter', 'Rogation Sunday', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (45, 'Ascension', 'E+39', 'Principal', 0, 'White', 'Ascension', 'Ascension Day', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (46, 'EasterVII', 'E+42', 'Sunday', 2, 'White', 'EasterVII', 'The Seventh Sunday of Easter', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (47, 'Pentecost', 'E+49', 'Principal', 0, 'Red', 'Pentecost', 'The Day of Pentecost', 'Whitsunday', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (48, 'TrinitySunday', 'E+56', 'Principal', 0, 'White', 'TrinitySunday', 'Trinity Sunday', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (49, 'AfterPentecostII', 'E+63', 'Sunday', 5, 'Green', '_', 'The Second Sunday After Pentecost', '_', 'Proper');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (50, 'AfterPentecostIII', 'E+70', 'Sunday', 5, 'Green', '_', 'The Third Sunday After Pentecost', '_', 'Proper');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (51, 'AfterPentecostIV', 'E+77', 'Sunday', 5, 'Green', '_', 'The Fourth Sunday After Pentecost', '_', 'Proper');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (52, 'AfterPentecostV', 'E+84', 'Sunday', 5, 'Green', '_', 'The Fifth Sunday After Pentecost', '_', 'Proper');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (53, 'AfterPentecostVI', 'E+91', 'Sunday', 5, 'Green', '_', 'The Sixth Sunday After Pentecost', '_', 'Proper');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (54, 'AfterPentecostVII', 'E+98', 'Sunday', 5, 'Green', '_', 'The Seventh Sunday After Pentecost', '_', 'Proper');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (55, 'AfterPentecostVIII', 'E+105', 'Sunday', 5, 'Green', '_', 'The Eighth Sunday After Pentecost', '_', 'Proper');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (56, 'AfterPentecostIX', 'E+112', 'Sunday', 5, 'Green', '_', 'The Ninth Sunday After Pentecost', '_', 'Proper');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (57, 'AfterPentecostX', 'E+119', 'Sunday', 5, 'Green', '_', 'The Tenth Sunday After Pentecost', '_', 'Proper');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (58, 'AfterPentecostXI', 'E+126', 'Sunday', 5, 'Green', '_', 'The Eleventh Sunday After Pentecost', '_', 'Proper');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (59, 'AfterPentecostXII', 'E+133', 'Sunday', 5, 'Green', '_', 'The Twelfth Sunday After Pentecost', '_', 'Proper');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (60, 'AfterPentecostXIII', 'E+140', 'Sunday', 5, 'Green', '_', 'The Thirteenth Sunday After Pentecost', '_', 'Proper');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (61, 'AfterPentecostXIV', 'E+147', 'Sunday', 5, 'Green', '_', 'The Fourteenth Sunday After Pentecost', '_', 'Proper');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (62, 'AfterPentecostXV', 'E+154', 'Sunday', 5, 'Green', '_', 'The Fifteenth Sunday After Pentecost', '_', 'Proper');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (63, 'AfterPentecostXVI', 'E+161', 'Sunday', 5, 'Green', '_', 'The Sixteenth Sunday After Pentecost', '_', 'Proper');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (64, 'AfterPentecostXVII', 'E+168', 'Sunday', 5, 'Green', '_', 'The Seventeenth Sunday After Pentecost', '_', 'Proper');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (65, 'AfterPentecostXVIII', 'E+175', 'Sunday', 5, 'Green', '_', 'The Eighteenth Sunday After Pentecost', '_', 'Proper');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (66, 'AfterPentecostXIX', 'E+182', 'Sunday', 5, 'Green', '_', 'The Nineteenth Sunday After Pentecost', '_', 'Proper');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (67, 'AfterPentecostXX', 'E+189', 'Sunday', 5, 'Green', '_', 'The Twentieth Sunday After Pentecost', '_', 'Proper');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (68, 'AfterPentecostXXI', 'E+196', 'Sunday', 5, 'Green', '_', 'The Twenty-First Sunday After Pentecost', '_', 'Proper');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (69, 'AfterPentecostXXII', 'E+203', 'Sunday', 5, 'Green', '_', 'The Twenty-Second Sunday After Pentecost', '_', 'Proper');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (70, 'AfterPentecostXXIII', 'E+210 (before 11/20→Sun)', 'Sunday', 5, 'Green', '_', 'The Twenty-Third Sunday After Pentecost', '_', 'Proper');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (71, 'AfterPentecostXXIV', 'E+217 (before 11/20→Sun)', 'Sunday', 5, 'Green', '_', 'The Twenty-Fourth Sunday After Pentecost', '_', 'Proper');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (72, 'AfterPentecostXXV', 'E+224 (before 11/20→Sun)', 'Sunday', 5, 'Green', '_', 'The Twenty-Fifth Sunday After Pentecost', '_', 'Proper');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (73, 'AfterPentecostXXVI', 'E+231 (before 11/20→Sun)', 'Sunday', 5, 'Green', '_', 'The Twenty-Sixth Sunday After Pentecost', '_', 'Proper');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (74, 'AfterPentecostXXVII', 'E+238 (before 11/20→Sun)', 'Sunday', 5, 'Green', '_', 'The Twenty-Seventh Sunday After Pentecost', '_', 'Proper');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (75, 'AfterPentecostUltima', '11/20→Sun', 'Sunday', 5, 'Green', 'Proper29', 'The Last Sunday After Pentecost', 'Christ the King', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (76, 'Andrew', '11/30', 'Major', 4, 'Red', 'Andrew', 'Andrew the Apostle', 'Andermas', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (77, 'Thomas', '12/21', 'Major', 4, 'Red', 'Thomas', 'Thomas the Apostle', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (78, 'Stephen', '12/26', 'Major', 4, 'Red', 'Stephen', 'Stephen, Deacon and Martyr', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (79, 'John', '12/27', 'Major', 4, 'White', 'John', 'John, Apostle and Evangelist', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (80, 'HolyInnocents', '12/28', 'Major', 4, 'Red', 'HolyInnocents', 'The Holy Innocents', 'Childermas', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (81, 'HolyName', '1/1', 'Major', 4, 'White', 'HolyName', 'The Circumcision and Holy Name of Our Lord Jesus Christ', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (82, 'ConfessionOfPeter', '1/18', 'Major', 4, 'White', 'Peter', 'Confession of Peter the Apostle', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (83, 'ConversionOfPaul', '1/25', 'Major', 4, 'White', 'Paul', 'Conversion of Paul the Apostle', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (84, 'Presentation', '2/2', 'Major', 4, 'White', 'Presentation', 'The Presentation of Our Lord Jesus Christ in the Temple', 'Candlemas', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (85, 'Matthias', '2/24', 'Major', 4, 'Red', 'Matthias', 'Matthias the Apostle', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (86, 'Joseph', '3/19', 'Major', 4, 'White', 'Joseph', 'Joseph, Husband of the Virgin Mary and Guardian of Jesus', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (87, 'Annunciation', '3/25', 'Major', 4, 'White', 'Annunciation', 'The Annunciation of Our Lord Jesus Christ to the Virgin Mary', 'Lady Day', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (88, 'Mark', '4/25', 'Major', 4, 'Red', 'Mark', 'Mark the Evangelist', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (89, 'PhilipJames', '5/1', 'Major', 4, 'Red', 'PhilipJames', 'Philip and James, Apostles', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (90, 'Visitation', '5/31', 'Major', 4, 'White', 'Visitation', 'The Visitation of the Virgin Mary to Elizabeth and Zechariah', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (91, 'Barnabas', '6/11', 'Major', 4, 'Red', 'Barnabas', 'Barnabas the Apostle', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (92, 'NativityOfJohnTheBaptist', '6/24', 'Major', 4, 'White', 'JohnTheBaptist', 'The Nativity of John the Baptist', 'Midsummer Day', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (93, 'PeterPaul', '6/29', 'Major', 4, 'Red', 'PeterPaul', 'Peter and Paul, Apostles', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (94, 'MaryMagdalene', '7/22', 'Major', 4, 'White', 'MaryMagdalene', 'Mary Magdalene', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (95, 'JamesSonOfZebedee', '7/25', 'Major', 4, 'Red', 'James', 'James the Elder, Apostle', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (96, 'Transfiguration', '8/6', 'Major', 4, 'White', 'Transfiguration', 'The Transfiguration of Our Lord Jesus Christ', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (97, 'Mary', '8/15', 'Major', 4, 'White', 'Mary', 'The Virgin Mary, Mother of Our Lord Jesus Christ', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (98, 'Bartholomew', '8/24', 'Major', 4, 'Red', 'Bartholomew', 'Bartholomew the Apostle', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (99, 'HolyCrossDay', '9/14', 'Major', 4, 'Red', 'HolyCrossDay', 'Holy Cross Day', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (100, 'Matthew', '9/21', 'Major', 4, 'Red', 'Matthew', 'Matthew, Apostle and Evangelist', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (101, 'Michael', '9/29', 'Major', 4, 'White', 'Michael', 'Holy Michael and All Angels', 'Michaelmas', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (102, 'Luke', '10/18', 'Major', 4, 'Red', 'Luke', 'Luke the Evangelist and Companion of Paul', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (103, 'JamesOfJerusalem', '10/23', 'Major', 4, 'Red', 'JamesOfJerusalem', 'James of Jerusalem, Bishop and Martyr, Brother of Our Lord', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (104, 'SimonJude', '10/28', 'Major', 4, 'Red', 'SimonJude', 'Simon and Jude, Apostles', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (105, 'AllSaints', '11/1', 'Principal', 0, 'White', 'AllSaints', 'All Saints’ Day', '_', 'AllSaints');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (106, 'WinterEmber', '12/14→Wed,12/16→Fri,12/17→Sat', 'Ember', 10, 'Purple', 'Ember', 'Ember Day', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (107, 'Ember', 'E-39,E-37,E-36,E+52,E+54,E+55,9/15→Wed,9/17→Fri,9/18→Sat', 'Ember', 10, 'Purple', '_', 'Ember Day', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (108, 'Rogation', 'E+36,E+37,E+38', 'Rogation', 10, 'White', 'Rogation', 'Rogation Day', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (109, 'MemorialDay', '5/25→Mon', 'National', 11, '_', 'Military', 'Memorial Day (United States)', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (110, 'CanadaDay', '7/1', 'National', 11, '_', 'CanadaDay', 'Canada Day (Canada)', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (111, 'IndependenceDay', '7/4', 'National', 11, '_', 'IndependenceDay', 'Independence Day (United States)', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (112, 'ThanksgivingCanada', '10/8→Mon', 'National', 11, '_', 'Thanksgiving', 'Thanksgiving Day (Canada)', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (113, 'RemembranceDay', '11/11', 'National', 11, '_', 'Military', 'Remembrance Day (Canada)', '_', '_');
INSERT OR REPLACE INTO holidays (id, handle, date_rule, style, priority, colour, propers, name, alternative_name, importable_fragments) VALUES (114, 'ThanksgivingUnitedStates', '11/22→Thu', 'National', 11, '_', 'Thanksgiving', 'Thanksgiving Day (United States)', '_', '_');

INSERT OR REPLACE INTO fragments (id, date_rule, behaviour, propers) VALUES (1, 'E-56', 'Append', 'EpiphanyPaenultima');
INSERT OR REPLACE INTO fragments (id, date_rule, behaviour, propers) VALUES (2, '11/1 (not on 11/1→Sun)', 'Append', 'AllSaintsWeekday');
INSERT OR REPLACE INTO fragments (id, date_rule, behaviour, propers) VALUES (3, '5/8→Sun', 'Append', 'Proper1');
INSERT OR REPLACE INTO fragments (id, date_rule, behaviour, propers) VALUES (4, '5/15→Sun', 'Append', 'Proper2');
INSERT OR REPLACE INTO fragments (id, date_rule, behaviour, propers) VALUES (5, '5/22→Sun', 'Append', 'Proper3');
INSERT OR REPLACE INTO fragments (id, date_rule, behaviour, propers) VALUES (6, '5/29→Sun', 'Append', 'Proper4');
INSERT OR REPLACE INTO fragments (id, date_rule, behaviour, propers) VALUES (7, '6/5→Sun', 'Append', 'Proper5');
INSERT OR REPLACE INTO fragments (id, date_rule, behaviour, propers) VALUES (8, '6/12→Sun', 'Append', 'Proper6');
INSERT OR REPLACE INTO fragments (id, date_rule, behaviour, propers) VALUES (9, '6/19→Sun', 'Append', 'Proper7');
INSERT OR REPLACE INTO fragments (id, date_rule, behaviour, propers) VALUES (10, '6/26→Sun', 'Append', 'Proper8');
INSERT OR REPLACE INTO fragments (id, date_rule, behaviour, propers) VALUES (11, '7/3→Sun', 'Append', 'Proper9');
INSERT OR REPLACE INTO fragments (id, date_rule, behaviour, propers) VALUES (12, '7/10→Sun', 'Append', 'Proper10');
INSERT OR REPLACE INTO fragments (id, date_rule, behaviour, propers) VALUES (13, '7/17→Sun', 'Append', 'Proper11');
INSERT OR REPLACE INTO fragments (id, date_rule, behaviour, propers) VALUES (14, '7/24→Sun', 'Append', 'Proper12');
INSERT OR REPLACE INTO fragments (id, date_rule, behaviour, propers) VALUES (15, '7/31→Sun', 'Append', 'Proper13');
INSERT OR REPLACE INTO fragments (id, date_rule, behaviour, propers) VALUES (16, '8/7→Sun', 'Append', 'Proper14');
INSERT OR REPLACE INTO fragments (id, date_rule, behaviour, propers) VALUES (17, '8/14→Sun', 'Append', 'Proper15');
INSERT OR REPLACE INTO fragments (id, date_rule, behaviour, propers) VALUES (18, '8/21→Sun', 'Append', 'Proper16');
INSERT OR REPLACE INTO fragments (id, date_rule, behaviour, propers) VALUES (19, '8/28→Sun', 'Append', 'Proper17');
INSERT OR REPLACE INTO fragments (id, date_rule, behaviour, propers) VALUES (20, '9/4→Sun', 'Append', 'Proper18');
INSERT OR REPLACE INTO fragments (id, date_rule, behaviour, propers) VALUES (21, '9/11→Sun', 'Append', 'Proper19');
INSERT OR REPLACE INTO fragments (id, date_rule, behaviour, propers) VALUES (22, '9/18→Sun', 'Append', 'Proper20');
INSERT OR REPLACE INTO fragments (id, date_rule, behaviour, propers) VALUES (23, '9/25→Sun', 'Append', 'Proper21');
INSERT OR REPLACE INTO fragments (id, date_rule, behaviour, propers) VALUES (24, '10/2→Sun', 'Append', 'Proper22');
INSERT OR REPLACE INTO fragments (id, date_rule, behaviour, propers) VALUES (25, '10/9→Sun', 'Append', 'Proper23');
INSERT OR REPLACE INTO fragments (id, date_rule, behaviour, propers) VALUES (26, '10/16→Sun', 'Append', 'Proper24');
INSERT OR REPLACE INTO fragments (id, date_rule, behaviour, propers) VALUES (27, '10/23→Sun', 'Append', 'Proper25');
INSERT OR REPLACE INTO fragments (id, date_rule, behaviour, propers) VALUES (28, '10/30→Sun', 'Append', 'Proper26');
INSERT OR REPLACE INTO fragments (id, date_rule, behaviour, propers) VALUES (29, '11/6→Sun', 'Append', 'Proper27');
INSERT OR REPLACE INTO fragments (id, date_rule, behaviour, propers) VALUES (30, '11/13→Sun', 'Append', 'Proper28');

INSERT OR REPLACE INTO subcycles (id, handle, epoch, order_value, full_cycle) VALUES (1, 'A', 2020, 0, 3);
INSERT OR REPLACE INTO subcycles (id, handle, epoch, order_value, full_cycle) VALUES (2, 'B', 2020, 1, 3);
INSERT OR REPLACE INTO subcycles (id, handle, epoch, order_value, full_cycle) VALUES (3, 'C', 2020, 2, 3);

COMMIT;
