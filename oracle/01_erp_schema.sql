/* =====================================================================================
   ERP (Oracle) - operational tables of a poultry processing company
   -------------------------------------------------------------------------------------
   This is the SOURCE system of the project: the ERP that the plants use every day.
   It is kept the way legacy ERPs usually are, on purpose:
     - Portuguese column names and codes (FORNECEDOR = supplier, UNIDADE = plant...)
     - no foreign keys between the operational tables (orphan records happen)
     - free text where a code would be better (stop reasons typed by hand)
     - DT_ATUALIZACAO (last update) on every table: the only way to read changes
   The data warehouse never changes these tables; it only reads them through Apache Hop.
   ===================================================================================== */

/* Plants (slaughterhouses). CAPACIDADE_AVES_DIA = birds processed per day */
CREATE TABLE UNIDADE (
    COD_UNIDADE          NUMBER(4)      NOT NULL,
    NOME                 VARCHAR2(60)   NOT NULL,
    CIDADE               VARCHAR2(60)   NOT NULL,
    UF                   CHAR(2)        NOT NULL,
    CAPACIDADE_AVES_DIA  NUMBER(8)      NOT NULL,
    DT_ATUALIZACAO       DATE           NOT NULL,
    CONSTRAINT PK_UNIDADE PRIMARY KEY (COD_UNIDADE)
);

/* Integrated poultry farms that deliver live birds to one plant.
   CNPJ is typed by hand: sometimes with the mask (12.345.678/0001-90), sometimes without,
   and a few farms were registered twice with two codes. SITUACAO: A = active, I = inactive */
CREATE TABLE FORNECEDOR (
    COD_FORNECEDOR       NUMBER(6)      NOT NULL,
    RAZAO_SOCIAL         VARCHAR2(100)  NOT NULL,
    CNPJ                 VARCHAR2(20)   NOT NULL,
    CIDADE               VARCHAR2(60)   NOT NULL,
    UF                   CHAR(2)        NOT NULL,
    COD_UNIDADE          NUMBER(4)      NOT NULL,
    DISTANCIA_KM         NUMBER(5)      NOT NULL,
    DT_INICIO_INTEGRACAO DATE           NOT NULL,
    SITUACAO             CHAR(1)        NOT NULL,
    DT_ATUALIZACAO       DATE           NOT NULL,
    CONSTRAINT PK_FORNECEDOR PRIMARY KEY (COD_FORNECEDOR)
);

/* Finished products. RENDIMENTO_PADRAO = expected share of the live weight that becomes
   this product (e.g. 0.18 = 18% of the live weight becomes breast fillet) */
CREATE TABLE PRODUTO (
    COD_PRODUTO          NUMBER(6)      NOT NULL,
    DESCRICAO            VARCHAR2(80)   NOT NULL,
    CATEGORIA            VARCHAR2(20)   NOT NULL,
    RENDIMENTO_PADRAO    NUMBER(5, 4)   NOT NULL,
    DT_ATUALIZACAO       DATE           NOT NULL,
    CONSTRAINT PK_PRODUTO PRIMARY KEY (COD_PRODUTO)
);

/* One truck load of live birds (a "lot") received from a farm.
   QT_MORTAS_TRANSPORTE = birds dead on arrival (DOA), the main animal-welfare indicator.
   STATUS: RECEBIDO = received, CANCELADO = load cancelled (no arrival date, no weights) */
CREATE TABLE RECEBIMENTO_LOTE (
    NR_LOTE              NUMBER(10)     NOT NULL,
    COD_FORNECEDOR       NUMBER(6)      NOT NULL,
    COD_UNIDADE          NUMBER(4)      NOT NULL,
    DT_PREVISTA          DATE           NOT NULL,
    DT_CHEGADA           DATE,
    QT_AVES              NUMBER(8),
    PESO_VIVO_KG         NUMBER(12, 2),
    QT_MORTAS_TRANSPORTE NUMBER(6),
    PESO_CONDENADO_KG    NUMBER(10, 2),
    STATUS               VARCHAR2(10)   NOT NULL,
    DT_ATUALIZACAO       DATE           NOT NULL,
    CONSTRAINT PK_RECEBIMENTO_LOTE PRIMARY KEY (NR_LOTE)
);

/* Production order: part of one lot processed into one product on one line */
CREATE TABLE ORDEM_PRODUCAO (
    NR_ORDEM             NUMBER(12)     NOT NULL,
    NR_LOTE              NUMBER(10)     NOT NULL,
    COD_UNIDADE          NUMBER(4)      NOT NULL,
    COD_PRODUTO          NUMBER(6)      NOT NULL,
    LINHA                NUMBER(2)      NOT NULL,
    DT_INICIO            DATE           NOT NULL,
    DT_FIM               DATE           NOT NULL,
    PESO_PLANEJADO_KG    NUMBER(12, 2)  NOT NULL,
    PESO_PRODUZIDO_KG    NUMBER(12, 2)  NOT NULL,
    DT_ATUALIZACAO       DATE           NOT NULL,
    CONSTRAINT PK_ORDEM_PRODUCAO PRIMARY KEY (NR_ORDEM)
);

/* Quality inspection of a sample of one production order. RESULTADO: A = approved, R = rejected */
CREATE TABLE INSPECAO_QUALIDADE (
    NR_INSPECAO          NUMBER(12)     NOT NULL,
    NR_ORDEM             NUMBER(12)     NOT NULL,
    DT_INSPECAO          DATE           NOT NULL,
    QT_AMOSTRA           NUMBER(5)      NOT NULL,
    QT_DEFEITOS          NUMBER(5)      NOT NULL,
    RESULTADO            CHAR(1)        NOT NULL,
    DT_ATUALIZACAO       DATE           NOT NULL,
    CONSTRAINT PK_INSPECAO_QUALIDADE PRIMARY KEY (NR_INSPECAO)
);

/* Line stops. MOTIVO (reason) is free text typed by the operator */
CREATE TABLE PARADA_LINHA (
    NR_PARADA            NUMBER(10)     NOT NULL,
    COD_UNIDADE          NUMBER(4)      NOT NULL,
    LINHA                NUMBER(2)      NOT NULL,
    DT_INICIO            DATE           NOT NULL,
    DT_FIM               DATE           NOT NULL,
    MOTIVO               VARCHAR2(60)   NOT NULL,
    DT_ATUALIZACAO       DATE           NOT NULL,
    CONSTRAINT PK_PARADA_LINHA PRIMARY KEY (NR_PARADA)
);

/* Change tracking: Hop reads only rows updated after the last successful load */
CREATE INDEX IX_FORNECEDOR_ATUALIZACAO ON FORNECEDOR (DT_ATUALIZACAO);
CREATE INDEX IX_RECEBIMENTO_ATUALIZACAO ON RECEBIMENTO_LOTE (DT_ATUALIZACAO);
CREATE INDEX IX_ORDEM_ATUALIZACAO ON ORDEM_PRODUCAO (DT_ATUALIZACAO);
CREATE INDEX IX_INSPECAO_ATUALIZACAO ON INSPECAO_QUALIDADE (DT_ATUALIZACAO);
CREATE INDEX IX_PARADA_ATUALIZACAO ON PARADA_LINHA (DT_ATUALIZACAO);
