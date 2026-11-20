"""BK-004: interface de página única para o fluxo compartilhado de atendimento."""

import streamlit as st

from vlab import comparison, profiles, service
from vlab.ai import AIError
from vlab.prompt_engine import (
    CONTENT_STRATEGIES, VERSION_INSTRUCTIONS, ResponseValidationError,
)
from vlab.storage import StorageError


PROFILE_IDS = ("ana", "bruno", "carla", "diego")
CONTENT_LABELS = {
    "diagnosis": "Diagnóstico",
    "resolution": "Resolução",
    "questions": "Perguntas de esclarecimento",
    "flow": "Fluxo de atendimento",
}
VERSION_LABELS = {"v1": "v1 — Baseline", "v2": "v2 — Otimizada"}


def profile_label(profile: dict) -> str:
    attributes = (
        profile["nivel_tecnico"], profile["estilo_comunicacao"], profile["canal"],
    )
    return f"{profile.get('nome', profile.get('id'))} — " + ", ".join(
        value.capitalize() for value in attributes
    )


def render_content(content: dict, content_type: str) -> None:
    """Apresenta apenas os quatro contratos já validados pelo motor."""
    if content_type == "diagnosis":
        for field, title in (
            ("hipoteses", "Hipóteses"),
            ("evidencias", "Evidências"),
            ("informacoes_faltantes", "Informações faltantes"),
        ):
            st.markdown(f"**{title}**")
            if content[field]:
                for item in content[field]:
                    st.markdown(f"- {item}")
            else:
                st.write("Nenhuma informação indicada.")
        st.markdown("**Conclusão**")
        st.write(content["conclusao"])
    elif content_type == "resolution":
        for step in content["passos"]:
            st.markdown(f"{step['ordem']}. {step['instrucao']}")
        st.markdown("**Verificação**")
        st.write(content["verificacao"])
    elif content_type == "questions":
        for question in content["perguntas"]:
            st.markdown(f"{question['prioridade']}. {question['pergunta']}")
    elif content_type == "flow":
        for decision in content["decisoes"]:
            st.markdown(f"**{decision['ordem']}. {decision['condicao']}**")
            st.write("Se sim: " + decision["se_sim"])
            st.write("Se não: " + decision["se_nao"])


def render_result(result: dict) -> None:
    st.divider()
    st.subheader("Resposta do atendimento")
    st.success("Atendimento concluído e histórico salvo.")
    render_content(result["conteudo"], result["tipo_conteudo"])

    st.subheader("Informações da execução")
    customer = result["cliente"]
    st.write("Cliente: " + customer.get("nome", customer.get("id", "")))
    st.write("Tipo de conteúdo: " + CONTENT_LABELS[result["tipo_conteudo"]])
    st.write("Versão do prompt: " + result["versao_prompt"])
    if result.get("modelo"):
        st.write("Modelo: " + result["modelo"])
    st.write(
        "Origem: cache (cache hit)" if result["cache_hit"]
        else "Origem: API OpenAI (cache miss)"
    )
    st.write("Histórico JSON desta execução:")
    st.code(result["history_path"], language=None)


def render_comparison(available_profiles: dict) -> None:
    st.divider()
    st.header("Comparação de prompts e rubrica")
    profile_id = st.selectbox(
        "Perfil para comparação", PROFILE_IDS, key="comparison_profile",
        format_func=lambda identifier: profile_label(available_profiles[identifier]),
    )
    ticket = st.text_area("Ticket para comparação", key="comparison_ticket", height=140)
    content_type = st.selectbox(
        "Tipo de conteúdo para comparação", tuple(CONTENT_STRATEGIES),
        format_func=CONTENT_LABELS.get, key="comparison_type",
    )
    current_scenario = {
        "perfil": available_profiles[profile_id], "ticket": ticket, "tipo_conteudo": content_type,
    }
    active = st.session_state.get("comparison")
    if active is not None and any(
        active["cenario"][field] != value for field, value in current_scenario.items()
    ):
        st.session_state.pop("comparison", None)
        st.session_state.pop("saved_comparison", None)
        st.info("Cenário alterado. Execute uma nova comparação antes de avaliar.")

    if st.button("Comparar v1 e v2", key="compare_prompts", type="primary"):
        st.session_state.pop("comparison", None)
        st.session_state.pop("saved_comparison", None)
        if not ticket.strip():
            st.error("Informe o problema do cliente antes de comparar.")
        else:
            try:
                with st.spinner("Gerando v1 e v2 e salvando os históricos..."):
                    st.session_state["comparison"] = comparison.run_comparison(
                        profiles.load_profile(profile_id), ticket, content_type,
                    )
            except (AIError, StorageError, ValueError):
                st.error(
                    "Comparação incompleta: não foi possível obter as duas respostas válidas. "
                    "Verifique o perfil, a configuração OpenAI e o diretório de armazenamento. "
                    "As execuções já concluídas mantêm seu cache e histórico."
                )

    active = st.session_state.get("comparison")
    if active is None:
        return
    st.caption("Comparação: " + active["comparison_id"])
    for column, version in zip(st.columns(2), comparison.VERSIONS):
        result = active["resultados"][version]
        with column:
            st.subheader("Prompt " + VERSION_LABELS[version])
            st.write("Modelo: " + result["modelo"])
            st.write("Origem: cache (cache hit)" if result["cache_hit"] else "Origem: API OpenAI")
            render_content(result["conteudo"], result["tipo_conteudo"])
            with st.expander("Metadados da execução " + version):
                st.write("Execução: " + result["execution_id"])
                st.code(result["history_path"], language=None)

    st.subheader("Rubrica manual")
    st.write("1 — Insuficiente · 2 — Fraco · 3 — Adequado · 4 — Bom · 5 — Excelente")
    st.caption("Os totais representam apenas a avaliação manual deste cenário, com máximo de 15 pontos.")
    saved = st.session_state.get("saved_comparison")
    evaluations = {}
    for column, version in zip(st.columns(2), comparison.VERSIONS):
        with column:
            st.markdown("**Avaliação " + version + "**")
            criteria = {}
            for criterion, (label, question) in comparison.CRITERIA.items():
                if saved is not None:
                    entry = saved["resultados"][version]["avaliacao"]["criteria"][criterion]
                    st.markdown(f"**{label}: {entry['score']}/5**")
                    st.write(entry["justification"])
                    criteria[criterion] = entry
                    continue
                prefix = f"{active['comparison_id']}_{version}_{criterion}"
                score = st.number_input(
                    f"Nota de {label} ({version})", min_value=1, max_value=5, value=3, step=1,
                    key=prefix + "_score", help=question,
                )
                justification = st.text_area(
                    f"Justificativa de {label} ({version})", key=prefix + "_justification",
                )
                criteria[criterion] = {"score": score, "justification": justification}
            evaluations[version] = criteria
    totals = {
        version: sum(entry["score"] for entry in criteria.values())
        for version, criteria in evaluations.items()
    }
    st.write(f"Total v1: {totals['v1']}/15 · Total v2: {totals['v2']}/15")
    st.write(f"Diferença v2 − v1: {totals['v2'] - totals['v1']:+d}")
    if st.button("Salvar avaliação", key="save_comparison", disabled=saved is not None):
        try:
            saved = comparison.save_comparison(active, evaluations)
            st.session_state["saved_comparison"] = saved
            # Exibe a rubrica persistida como leitura após confirmar a gravação.
            st.rerun()
        except ValueError as error:
            st.error(str(error))
        except StorageError:
            st.error("Não foi possível salvar a comparação. Verifique o diretório e tente novamente.")
    if saved is not None:
        st.success("Avaliação salva. Comparação: " + saved["comparison_id"])
        st.write(f"Totais salvos — v1: {saved['totais']['v1']}/15 · v2: {saved['totais']['v2']}/15")
        st.write("JSON da comparação:")
        st.code(saved["comparison_path"], language=None)


def main() -> None:
    st.set_page_config(page_title="Vlab — Atendimento", page_icon="💬")
    st.title("Vlab — Assistente de suporte")
    st.write("Gere orientações de suporte adaptadas ao perfil do cliente e ao problema relatado.")

    try:
        available_profiles = {
            identifier: profiles.load_profile(identifier) for identifier in PROFILE_IDS
        }
    except profiles.ProfileError:
        st.error("Não foi possível carregar os perfis. Verifique os arquivos JSON em profiles/.")
        return

    with st.form("atendimento"):
        st.subheader("Configurar atendimento")
        profile_id = st.selectbox(
            "Perfil do cliente", PROFILE_IDS, key="profile_id",
            format_func=lambda identifier: profile_label(available_profiles[identifier]),
        )
        ticket = st.text_area(
            "Ticket — problema relatado", key="ticket", height=140,
            placeholder="Descreva o problema do cliente...",
        )
        content_type = st.selectbox(
            "Tipo de conteúdo", tuple(CONTENT_STRATEGIES),
            format_func=CONTENT_LABELS.get, key="content_type",
        )
        version = st.selectbox(
            "Versão do prompt", tuple(VERSION_INSTRUCTIONS), index=1,
            format_func=VERSION_LABELS.get, key="version",
        )
        submitted = st.form_submit_button("Gerar resposta", type="primary")

    if submitted:
        # Uma falha da nova solicitação não deve exibir o sucesso da anterior.
        st.session_state.pop("last_result", None)
        if not ticket.strip():
            st.error("Informe o problema do cliente antes de gerar a resposta.")
        else:
            try:
                with st.spinner("Gerando resposta e salvando histórico..."):
                    result = service.run_generation(
                        profiles.load_profile(profile_id), ticket, content_type, version,
                    )
                st.session_state["last_result"] = result
            except profiles.ProfileError:
                st.error("Perfil inválido ou indisponível. Verifique o arquivo JSON do cliente.")
            except ResponseValidationError:
                st.error("A IA retornou uma resposta inválida. Tente gerar novamente.")
            except AIError:
                st.error(
                    "Não foi possível obter a resposta da OpenAI. Verifique a configuração "
                    "local, a conexão e o acesso da conta antes de tentar novamente."
                )
            except StorageError:
                st.error(
                    "Falha ao acessar o cache ou salvar o histórico. "
                    "Verifique o diretório de armazenamento e suas permissões."
                )
            except ValueError:
                st.error("Dados inválidos. Verifique o ticket, o tipo de conteúdo e a versão do prompt.")

    if st.session_state.get("last_result") is not None:
        render_result(st.session_state["last_result"])

    render_comparison(available_profiles)


if __name__ == "__main__":
    main()
