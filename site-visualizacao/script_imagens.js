// Configuração: Caminho da sua pasta de imagens no servidor
const URL_IMAGENS = './imagens/BU'; 

async function construirGaleriaDinamica() {
  const container = document.getElementById('galeria');
  if (!container) return;

  try {
    container.innerHTML = 'Carregando estrutura de imagens...';

    // 1. Acessa a pasta "imagens/" do servidor para ler o HTML de listagem
    const resposta = await fetch(URL_IMAGENS);
    if (!resposta.ok) throw new Error('Não foi possível listar a pasta raiz.');
    const htmlRaiz = await resposta.text();

    // 2. Transforma o texto em HTML manipulável e extrai os links das pastas
    const parser = new DOMParser();
    const docRaiz = parser.parseFromString(htmlRaiz, 'text/html');
    const links = Array.from(docRaiz.querySelectorAll('a')).map(a => a.getAttribute('href'));

    // SALVA OS NOMES EM UMA LISTA (Filtrando apenas links de pastas reais)
    const listaDePastas = links.filter(link => link.endsWith('/') && !link.includes('..') && link !== '/');

    if (listaDePastas.length === 0) {
      container.innerHTML = 'Nenhuma subpasta encontrada dentro de "imagens/".';
      return;
    }

    container.innerHTML = ''; // Limpa o texto de carregamento

    // 3. Loop principal: passa por cada pasta da lista criada
    for (const nomeDaPasta of listaDePastas) {
      const urlSubPasta = new URL(nomeDaPasta, new URL(URL_IMAGENS, window.location.href)).href;

      // Busca o conteúdo de dentro desta subpasta específica
      const respostaSub = await fetch(urlSubPasta);
      if (!respostaSub.ok) continue;
      const htmlSub = await respostaSub.text();

      const docSub = parser.parseFromString(htmlSub, 'text/html');
      const linksArquivos = Array.from(docSub.querySelectorAll('a')).map(a => a.getAttribute('href'));

      // Filtra apenas arquivos que sejam imagens
      const listaImagens = linksArquivos.filter(arquivo => /\.(jpe?g|png|gif|webp|svg)\$/i.test(arquivo));

      // Se a pasta tiver imagens, cria a estrutura exatamente como você pediu
      if (listaImagens.length > 0) {
        
        // Seção para envelopar a pasta atual
        const secaoPasta = document.createElement('section');
        secaoPasta.style.marginBottom = '30px';

        // REQUISITO: Um título com o nome da pasta
        const tituloPasta = document.createElement('h1');
        tituloPasta.textContent = `📁 Pasta: ${decodeURIComponent(nomeDaPasta).replace('/', '')}`;
        secaoPasta.appendChild(tituloPasta);

        // REQUISITO: Sequência de Título (h2) do arquivo + Imagem
        listaImagens.forEach(nomeDoArquivo => {
          const urlFinalImagem = new URL(nomeDoArquivo, urlSubPasta).href;

          // Bloco contenedor para cada dupla (Título + Foto)
          const blocoItem = document.createElement('div');
          blocoItem.style.margin = '20px 0';

          // - - Titulo (h2) com o nome do arquivo
          const tituloArquivo = document.createElement('h2');
          tituloArquivo.style.fontSize = '1.2rem';
          tituloArquivo.textContent = decodeURIComponent(nomeDoArquivo);
          blocoItem.appendChild(tituloArquivo);

          // - - A imagem
          const elementoImg = document.createElement('img');
          elementoImg.src = urlFinalImagem;
          elementoImg.alt = nomeDoArquivo;
          elementoImg.style.maxWidth = '100%';
          elementoImg.style.height = 'auto';
          blocoItem.appendChild(elementoImg);

          // Adiciona a sequência na seção da pasta
          secaoPasta.appendChild(blocoItem);
        });

        // Insere a pasta estruturada no container principal da tela
        container.appendChild(secaoPasta);
      }
    }

  } catch (erro) {
    console.error('Erro na geração da galeria:', erro);
    container.innerHTML = 'Erro ao mapear o servidor. Verifique o console.';
  }
}

// Executa automaticamente assim que a página HTML carregar
window.addEventListener('DOMContentLoaded', construirGaleriaDinamica);
