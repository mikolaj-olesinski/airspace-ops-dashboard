-- Utworzenie schematu dla hurtowni danych lotów
CREATE SCHEMA FlightDelayDW;
GO

-- Tabele pomocnicze dla wymiarów czasowych

-- Tabela pomocnicza dni tygodnia
CREATE TABLE FlightDelayDW.DayHelper (
    DayID INT PRIMARY KEY,
    Name VARCHAR(20) NOT NULL
);

-- Tabela pomocnicza miesięcy
CREATE TABLE FlightDelayDW.MonthHelper (
    MonthID INT PRIMARY KEY,
    Name VARCHAR(20) NOT NULL
);

-- Tabele wymiarów

-- Tabela wymiaru czasu
CREATE TABLE FlightDelayDW.DIM_TIME (
    TimeID INT PRIMARY KEY,
    Year INT NOT NULL,
    Quarter INT NOT NULL,
    Month INT NOT NULL,
    MonthName VARCHAR(20) NOT NULL,
    Day INT NOT NULL,
    DayOfWeek INT NOT NULL,
    DayName VARCHAR(20) NOT NULL,
    Weekend BIT NOT NULL,
    Season VARCHAR(10) NOT NULL,
    Hour INT NOT NULL,
    TimeOfDay VARCHAR(15) NOT NULL
);

-- Tabela wymiaru linii lotniczych
CREATE TABLE FlightDelayDW.DIM_AIRLINE (
    AirlineID INT IDENTITY(1,1) PRIMARY KEY,
    IATA_Code VARCHAR(5) NOT NULL,
    AirlineName VARCHAR(50) NOT NULL
);

-- Tabela wymiaru lotnisk
CREATE TABLE FlightDelayDW.DIM_AIRPORT (
    AirportID INT IDENTITY(1,1) PRIMARY KEY,
    IATA_Code VARCHAR(5) NOT NULL,
    City VARCHAR(50) NOT NULL,
    State VARCHAR(20) NOT NULL,
    Latitude FLOAT NULL,
    Longitude FLOAT NULL
);

-- Tabela wymiaru lotów
CREATE TABLE FlightDelayDW.DIM_FLIGHT (
    FlightID INT IDENTITY(1,1) PRIMARY KEY,
    FlightNumber INT NOT NULL,
    TailNumber VARCHAR(10) NOT NULL,
    Distance INT NOT NULL,
    ScheduledTime INT NOT NULL,
    DistanceGroup VARCHAR(10) NOT NULL,
    OriginAirport VARCHAR(5) NOT NULL,
    DestinationAirport VARCHAR(5) NOT NULL
);

-- Tabela wymiaru warunków pogodowych
CREATE TABLE FlightDelayDW.DIM_WEATHER (
    WeatherID INT IDENTITY(1,1) PRIMARY KEY,
    Temperature FLOAT NOT NULL,
    TempGroup VARCHAR(15) NOT NULL,
    Humidity FLOAT NOT NULL,
    HumidityGroup VARCHAR(15) NOT NULL,
    Visibility FLOAT NOT NULL,
    VisibilityGroup VARCHAR(15) NOT NULL,
    WindSpeed INT NOT NULL,
    WindGroup VARCHAR(15) NOT NULL,
    SkyCover VARCHAR(10) NOT NULL,
    SkyGroup VARCHAR(15) NOT NULL,
    WeatherCondition VARCHAR(20) NOT NULL,
    WeatherGroup VARCHAR(15) NOT NULL,
    Pressure FLOAT NOT NULL,
    PressureGroup VARCHAR(15) NOT NULL
);

-- Tabela faktów opóźnień lotów
CREATE TABLE FlightDelayDW.FACT_FLIGHT_DELAY (
    FactID INT IDENTITY(1,1) PRIMARY KEY,
    TimeID_Departure INT NOT NULL,
    TimeID_Arrival INT NOT NULL,
    TimeID_ScheduledDeparture INT NOT NULL,
    TimeID_ScheduledArrival INT NOT NULL,
    AirlineID INT NOT NULL,
    OriginAirportID INT NOT NULL,
    DestinationAirportID INT NOT NULL,
    FlightID INT NOT NULL,
    WeatherID_Origin INT NULL,
    WeatherID_Destination INT NULL,
    Distance INT NOT NULL,
    DepartureDelay FLOAT NOT NULL,
    TaxiOut INT NOT NULL,
    ArrivalDelay FLOAT NOT NULL,
    TaxiIn INT NOT NULL,
    ElapsedTime INT NOT NULL,
    AirTime INT NOT NULL,
    Cancelled BIT NOT NULL,
    Diverted BIT NOT NULL,
    AirSystemDelay INT NOT NULL,
    SecurityDelay INT NOT NULL,
    AirlineDelay INT NOT NULL,
    LateAircraftDelay INT NOT NULL,
    WeatherDelay INT NOT NULL,
    
    -- Klucze obce
    CONSTRAINT FK_FACT_TimeIDDeparture FOREIGN KEY (TimeID_Departure) 
        REFERENCES FlightDelayDW.DIM_TIME (TimeID),
    CONSTRAINT FK_FACT_TimeIDArrival FOREIGN KEY (TimeID_Arrival) 
        REFERENCES FlightDelayDW.DIM_TIME (TimeID),
    CONSTRAINT FK_FACT_TimeIDScheduledDeparture FOREIGN KEY (TimeID_ScheduledDeparture) 
        REFERENCES FlightDelayDW.DIM_TIME (TimeID),
    CONSTRAINT FK_FACT_TimeIDScheduledArrival FOREIGN KEY (TimeID_ScheduledArrival) 
        REFERENCES FlightDelayDW.DIM_TIME (TimeID),
    CONSTRAINT FK_FACT_AirlineID FOREIGN KEY (AirlineID) 
        REFERENCES FlightDelayDW.DIM_AIRLINE (AirlineID),
    CONSTRAINT FK_FACT_OriginAirportID FOREIGN KEY (OriginAirportID) 
        REFERENCES FlightDelayDW.DIM_AIRPORT (AirportID),
    CONSTRAINT FK_FACT_DestinationAirportID FOREIGN KEY (DestinationAirportID) 
        REFERENCES FlightDelayDW.DIM_AIRPORT (AirportID),
    CONSTRAINT FK_FACT_FlightID FOREIGN KEY (FlightID) 
        REFERENCES FlightDelayDW.DIM_FLIGHT (FlightID),
    CONSTRAINT FK_FACT_WeatherIDOrigin FOREIGN KEY (WeatherID_Origin) 
        REFERENCES FlightDelayDW.DIM_WEATHER (WeatherID),
    CONSTRAINT FK_FACT_WeatherIDDestination FOREIGN KEY (WeatherID_Destination) 
        REFERENCES FlightDelayDW.DIM_WEATHER (WeatherID)
);

-- Wypełnienie tabel pomocniczych

-- Wypełnienie tabeli dni tygodnia
INSERT INTO FlightDelayDW.DayHelper (DayID, Name) VALUES 
(1, 'Poniedziałek'),
(2, 'Wtorek'),
(3, 'Środa'),
(4, 'Czwartek'),
(5, 'Piątek'),
(6, 'Sobota'),
(7, 'Niedziela');

-- Wypełnienie tabeli miesięcy
INSERT INTO FlightDelayDW.MonthHelper (MonthID, Name) VALUES 
(1, 'Styczeń'),
(2, 'Luty'),
(3, 'Marzec'),
(4, 'Kwiecień'),
(5, 'Maj'),
(6, 'Czerwiec'),
(7, 'Lipiec'),
(8, 'Sierpień'),
(9, 'Wrzesień'),
(10, 'Październik'),
(11, 'Listopad'),
(12, 'Grudzień');





    -- -- Klucze obce
    -- CONSTRAINT FK_FACT_TimeIDDeparture FOREIGN KEY (TimeID_Departure) 
    --     REFERENCES FlightDelayDW.DIM_TIME (TimeID),
    -- CONSTRAINT FK_FACT_TimeIDArrival FOREIGN KEY (TimeID_Arrival) 
    --     REFERENCES FlightDelayDW.DIM_TIME (TimeID),
    -- CONSTRAINT FK_FACT_TimeIDScheduledDeparture FOREIGN KEY (TimeID_ScheduledDeparture) 
    --     REFERENCES FlightDelayDW.DIM_TIME (TimeID),
    -- CONSTRAINT FK_FACT_TimeIDScheduledArrival FOREIGN KEY (TimeID_ScheduledArrival) 
    --     REFERENCES FlightDelayDW.DIM_TIME (TimeID),
    -- CONSTRAINT FK_FACT_AirlineID FOREIGN KEY (AirlineID) 
    --     REFERENCES FlightDelayDW.DIM_AIRLINE (AirlineID),
    -- CONSTRAINT FK_FACT_OriginAirportID FOREIGN KEY (OriginAirportID) 
    --     REFERENCES FlightDelayDW.DIM_AIRPORT (AirportID),
    -- CONSTRAINT FK_FACT_DestinationAirportID FOREIGN KEY (DestinationAirportID) 
    --     REFERENCES FlightDelayDW.DIM_AIRPORT (AirportID),
    -- CONSTRAINT FK_FACT_FlightID FOREIGN KEY (FlightID) 
    --     REFERENCES FlightDelayDW.DIM_FLIGHT (FlightID),
    -- CONSTRAINT FK_FACT_WeatherIDOrigin FOREIGN KEY (WeatherID_Origin) 
    --     REFERENCES FlightDelayDW.DIM_WEATHER (WeatherID),
    -- CONSTRAINT FK_FACT_WeatherIDDestination FOREIGN KEY (WeatherID_Destination) 
    --     REFERENCES FlightDelayDW.DIM_WEATHER (WeatherID)