import sys
from datetime import datetime, timezone
from sqlalchemy import text
from feedin import app, database
from feedin.models import MarcacaoPostagem


def executar_automacao_completa():
    """
    Executa o ciclo completo de atualização do banco de dados:
    1. Cria as novas tabelas estruturais (Notificacao, MarcacaoPostagem, Desconexoes, Bloqueios).
    2. Migra os dados da tabela antiga para a nova com status controlado.
    3. Remove a tabela antiga do banco de dados de forma segura.
    Everything wrapped in a safe application context.
    """
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Iniciando processo de migração mestre...")

    with app.app_context():
        # =========================================================================
        # PASSO 1: CRIAÇÃO DAS NOVAS TABELAS
        # =========================================================================
        print("\nPasso 1: Validando e criando novas estruturas de tabelas...")
        try:
            # O SQLAlchemy detecta os novos modelos importados e cria apenas o que não existe
            database.create_all()
            print("-> Novas tabelas criadas ou validadas com sucesso!")
        except Exception as e:
            print(f"CRÍTICO: Falha ao criar tabelas no banco de dados: {e}")
            sys.exit(1)

        # =========================================================================
        # PASSO 2: MIGRAÇÃO DOS DADOS EXISTENTES (TRANSAÇÃO CONTROLADA)
        # =========================================================================
        print("\nPasso 2: Iniciando migração de dados de 'postagem_marcacoes'...")

        # Uso do Inspector do SQLAlchemy: Funciona de forma universal (SQLite, Postgres, MySQL)
        from sqlalchemy import inspect
        inspector = inspect(database.engine)
        tabela_antiga_existe = 'postagem_marcacoes' in inspector.get_table_names()

        if not tabela_antiga_existe:
            print("-> Aviso: A tabela 'postagem_marcacoes' não foi encontrada no banco. Pulando migração de dados.")
        else:
            try:
                # Busca os dados brutos da tabela antiga
                dados_antigos = database.session.execute(
                    text("SELECT id_postagem, id_usuario FROM postagem_marcacoes")
                ).fetchall()

                if not dados_antigos:
                    print("-> Nenhuma marcação antiga encontrada para migrar.")
                else:
                    contador = 0
                    for linha in dados_antigos:
                        id_post = linha[0]
                        id_user = linha[1]

                        # Evita duplicidade se rodado novamente por engano
                        ja_migrado = MarcacaoPostagem.query.filter_by(
                            postagem_id=id_post,
                            usuario_id=id_user
                        ).first()

                        if not ja_migrado:
                            nova_marcacao = MarcacaoPostagem(
                                postagem_id=id_post,
                                usuario_id=id_user,
                                solicitante_id=id_user,  # Histórico assume o próprio usuário
                                status='aceito',
                                criado_em=datetime.now(timezone.utc)
                            )
                            database.session.add(nova_marcacao)
                            contador += 1

                    # Commita a inclusão dos dados na tabela nova
                    database.session.commit()
                    print(
                        f"-> Sucesso! {contador} marcações migradas para 'marcacoes_postagens' com status 'aceito'.")

            except Exception as e:
                database.session.rollback()
                print(f"CRÍTICO: Erro durante a transferência de dados. Operação abortada: {e}")
                sys.exit(1)

        # =========================================================================
        # PASSO 3: REMOÇÃO DA ESTRUTURA LEGADA (CLEANUP)
        # =========================================================================
        print("\nPasso 3: Iniciando a remoção da tabela antiga do catálogo...")
        if tabela_antiga_existe:
            try:
                # Remove a tabela antiga fisicamente do banco de dados
                database.session.execute(text("DROP TABLE postagem_marcacoes"))
                database.session.commit()
                print("-> Sucesso! Tabela legada 'postagem_marcacoes' excluída definitivamente.")
            except Exception as e:
                database.session.rollback()
                print(f"AVISO: Os dados foram migrados, mas a tabela antiga não pôde ser excluída: {e}")
                print("Você pode removê-la manualmente mais tarde usando 'DROP TABLE postagem_marcacoes;'.")
        else:
            print("-> Limpeza não necessária (tabela já não existia).")

        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] --- PROCESSO CONCLUÍDO COM SUCESSO! ---")


if __name__ == "__main__":
    # Garante proteção mecânica: Pergunta antes de rodar se o comando for executado diretamente
    confirmacao = input("Deseja executar a migração mestre automática agora? (s/N): ")
    if confirmacao.lower() == 's':
        executar_automacao_completa()
    else:
        print("Operação cancelada pelo desenvolvedor.")