import sys
from datetime import datetime
from sqlalchemy import text, inspect
from feedin import app, database
from feedin.models import MarcacaoPostagem


def executar_automacao_completa():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Iniciando processo de migração mestre...")

    with app.app_context():
        # =========================================================================
        # PASSO 1: CRIAÇÃO DAS NOVAS TABELAS (Já validado!)
        # =========================================================================
        print("\nPasso 1: Validando e criando novas estruturas de tabelas...")
        try:
            database.create_all()
            print("-> Novas tabelas criadas ou validadas com sucesso!")
        except Exception as e:
            print(f"CRÍTICO: Falha ao criar tabelas: {e}")
            sys.exit(1)

        # =========================================================================
        # PASSO 2: MIGRAÇÃO DINÂMICA DOS DADOS EXISTENTES
        # =========================================================================
        print("\nPasso 2: Iniciando migração de dados de 'postagem_marcacoes'...")

        inspector = inspect(database.engine)
        tabela_antiga_existe = 'postagem_marcacoes' in inspector.get_table_names()

        if not tabela_antiga_existe:
            print("-> Aviso: A tabela 'postagem_marcacoes' não foi encontrada. Pulando migração.")
        else:
            try:
                # 1. Descobre dinamicamente os nomes das colunas existentes na tabela antiga
                colunas = [c['name'] for c in inspector.get_columns('postagem_marcacoes')]
                print(f"-> Colunas detectadas na tabela antiga: {colunas}")

                # Identifica qual coluna é do post e qual é do usuário mapeando por aproximação de nome
                col_post = next((c for c in colunas if 'post' in c.lower()), colunas[0])
                col_user = next((c for c in colunas if 'user' in c.lower() or 'usu' in c.lower()), colunas[1])

                print(f"-> Mapeando: Lendo dados de '{col_post}' e '{col_user}'...")

                # 2. Busca os dados usando os nomes reais que o banco reportou
                dados_antigos = database.session.execute(
                    text(f"SELECT {col_post}, {col_user} FROM postagem_marcacoes")
                ).fetchall()

                if not dados_antigos:
                    print("-> Nenhuma marcação antiga encontrada para migrar.")
                else:
                    contador = 0
                    for linha in dados_antigos:
                        id_post = linha[0]
                        id_user = linha[1]

                        # Evita duplicidade
                        ja_migrado = MarcacaoPostagem.query.filter_by(
                            postagem_id=id_post,
                            usuario_id=id_user
                        ).first()

                        if not ja_migrado:
                            nova_marcacao = MarcacaoPostagem(
                                postagem_id=id_post,
                                usuario_id=id_user,
                                solicitante_id=id_user,
                                status='aceito'
                            )
                            database.session.add(nova_marcacao)
                            contador += 1

                    database.session.commit()
                    print(f"-> Sucesso! {contador} marcações antigas migradas com status 'aceito'.")

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
                database.session.remove()
                database.session.execute(text("DROP TABLE postagem_marcacoes"))
                database.session.commit()
                print("-> Sucesso! Tabela legada 'postagem_marcacoes' excluída definitivamente.")
            except Exception as e:
                database.session.rollback()
                print(f"AVISO: Os dados foram migrados, mas a tabela antiga não pôde ser excluída: {e}")
        else:
            print("-> Limpeza não necessária.")

        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] --- PROCESSO CONCLUÍDO COM SUCESSO! ---")


if __name__ == "__main__":
    confirmacao = input("Deseja executar a migração mestre automática agora? (s/N): ")
    if confirmacao.lower() == 's':
        executar_automacao_completa()
    else:
        print("Operação cancelada.")