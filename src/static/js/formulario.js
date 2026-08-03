/*
 * Máscaras de digitação e busca de CEP.
 *
 * JavaScript próprio, sem biblioteca externa (AGENTS.md §2). Tudo aqui é
 * conveniência: se o script falhar, os campos continuam funcionando, e o
 * servidor valida de novo o que chegar.
 */
(function () {
  "use strict";

  function apenasDigitos(texto) {
    return (texto || "").replace(/\D/g, "");
  }

  var mascaras = {
    data: function (valor) {
      var d = apenasDigitos(valor).slice(0, 8);
      if (d.length > 4) return d.slice(0, 2) + "/" + d.slice(2, 4) + "/" + d.slice(4);
      if (d.length > 2) return d.slice(0, 2) + "/" + d.slice(2);
      return d;
    },
    hora: function (valor) {
      var d = apenasDigitos(valor).slice(0, 4);
      return d.length > 2 ? d.slice(0, 2) + ":" + d.slice(2) : d;
    },
    cep: function (valor) {
      var d = apenasDigitos(valor).slice(0, 8);
      return d.length > 5 ? d.slice(0, 5) + "-" + d.slice(5) : d;
    },
    documento: function (valor) {
      var d = apenasDigitos(valor).slice(0, 14);
      // Até 11 dígitos é CPF; acima disso, CNPJ.
      if (d.length <= 11) {
        return d
          .replace(/(\d{3})(\d)/, "$1.$2")
          .replace(/(\d{3})(\d)/, "$1.$2")
          .replace(/(\d{3})(\d{1,2})$/, "$1-$2");
      }
      return d
        .replace(/^(\d{2})(\d)/, "$1.$2")
        .replace(/^(\d{2})\.(\d{3})(\d)/, "$1.$2.$3")
        .replace(/\.(\d{3})(\d)/, ".$1/$2")
        .replace(/(\d{4})(\d{1,2})$/, "$1-$2");
    },
    telefone: function (valor) {
      var d = apenasDigitos(valor).slice(0, 11);
      if (d.length > 10) return "(" + d.slice(0, 2) + ") " + d.slice(2, 7) + "-" + d.slice(7);
      if (d.length > 6) return "(" + d.slice(0, 2) + ") " + d.slice(2, 6) + "-" + d.slice(6);
      if (d.length > 2) return "(" + d.slice(0, 2) + ") " + d.slice(2);
      return d;
    },
  };

  // Colar uma data inteira precisa funcionar: aplicamos a máscara ao valor
  // completo, em vez de bloquear a digitação tecla a tecla.
  document.querySelectorAll("[data-mascara]").forEach(function (campo) {
    var aplicar = mascaras[campo.dataset.mascara];
    if (!aplicar) return;

    function formatar() {
      var antes = campo.value;
      var depois = aplicar(antes);
      if (antes !== depois) campo.value = depois;
    }

    campo.addEventListener("input", formatar);
    campo.addEventListener("paste", function () {
      window.setTimeout(formatar, 0);
    });
    formatar();
  });

  /*
   * Campos que só valem para certos tipos de documento: "qual documento"
   * aparece só para identificação; "data de emissão", só onde ela define
   * validade. O servidor revalida — isto aqui é só para não poluir a tela.
   */
  var seletorTipo = document.querySelector("[data-controla-campos]");
  if (seletorTipo) {
    var config = document.getElementById("config-campos-documento");
    var comSubtipo = [];
    var comEmissao = [];
    if (config) {
      try {
        var dados = JSON.parse(config.textContent);
        comSubtipo = dados.subtipo || [];
        comEmissao = dados.emissao || [];
      } catch (erro) {
        /* Sem configuração legível: mostramos tudo, que é o comportamento seguro. */
      }
    }

    var blocos = {};
    document.querySelectorAll("[data-depende-de]").forEach(function (campo) {
      var bloco = campo.closest(".campo");
      if (bloco) blocos[campo.dataset.dependeDe] = { bloco: bloco, campo: campo };
    });

    function atualizar() {
      var tipo = parseInt(seletorTipo.value, 10);
      var pares = [
        ["identificacao", comSubtipo],
        ["emissao", comEmissao],
      ];

      pares.forEach(function (par) {
        var alvo = blocos[par[0]];
        if (!alvo) return;
        // Sem tipo escolhido, nada de campo condicional na tela.
        var aplica = Boolean(seletorTipo.value) && par[1].indexOf(tipo) !== -1;
        alvo.bloco.hidden = !aplica;
        // Campo escondido não deve enviar valor antigo.
        if (!aplica) alvo.campo.value = "";
      });
    }

    seletorTipo.addEventListener("change", atualizar);
    atualizar();
  }

  /*
   * Ações destrutivas pedem confirmação. Se o JS falhar, o envio acontece —
   * por isso a view também recusa excluir documento já aprovado.
   */
  document.querySelectorAll("form[data-confirmar]").forEach(function (form) {
    form.addEventListener("submit", function (evento) {
      if (!window.confirm(form.dataset.confirmar)) evento.preventDefault();
    });
  });

  /*
   * Linha inteira da tabela clicável. O link continua existindo dentro da
   * célula, para navegação por teclado e para abrir em nova aba.
   */
  document.querySelectorAll("tr[data-href]").forEach(function (linha) {
    linha.addEventListener("click", function (evento) {
      // Clique em link, botão ou seleção de texto não deve navegar duas vezes.
      if (evento.target.closest("a, button, input, label")) return;
      if (window.getSelection && String(window.getSelection())) return;
      window.location = linha.dataset.href;
    });
  });

  var campoCep = document.querySelector("[data-busca-cep]");
  if (!campoCep) return;

  var url = campoCep.dataset.url || "/solicitacoes/cep/";
  var alvos = ["logradouro", "bairro", "cidade", "uf"];

  campoCep.addEventListener("blur", function () {
    var cep = apenasDigitos(campoCep.value);
    if (cep.length !== 8) return;

    campoCep.classList.add("campo--carregando");

    fetch(url + "?cep=" + cep, { headers: { "X-Requested-With": "fetch" } })
      .then(function (resposta) {
        return resposta.ok ? resposta.json() : null;
      })
      .then(function (dados) {
        if (!dados || !dados.encontrado) return;
        alvos.forEach(function (nome) {
          var campo = document.getElementById("id_" + nome);
          // Não sobrescreve o que a pessoa já digitou.
          if (campo && !campo.value) campo.value = dados[nome] || "";
        });
        var numero = document.getElementById("id_numero");
        if (numero && !numero.value) numero.focus();
      })
      .catch(function () {
        /* Serviço fora do ar: o usuário digita o endereço à mão. */
      })
      .finally(function () {
        campoCep.classList.remove("campo--carregando");
      });
  });
})();
