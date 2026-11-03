import { render } from "preact";
import { LocationProvider, Route, Router } from "preact-iso";
import { Header, Toasts } from "./components";
import { loadBooks, loadCatalog, loadMy } from "./data";
import { BooksPage } from "./pages/books";
import { CatalogPage } from "./pages/catalog";
import { FilmPage } from "./pages/film";
import { ListsPage } from "./pages/lists";
import { PersonPage } from "./pages/person";
import { SearchPage } from "./pages/search";
import "./style.css";

loadMy();
loadBooks();
loadCatalog();

function NotFound() {
  return (
    <main class="pad">
      <p>Такой страницы нет. <a href="/">Вернуться к спискам</a></p>
    </main>
  );
}

function App() {
  return (
    <LocationProvider>
      <Header />
      <Router>
        <Route path="/" component={ListsPage} />
        <Route path="/film/:id" component={FilmPage} />
        <Route path="/person/:id" component={PersonPage} />
        <Route path="/catalog" component={CatalogPage} />
        <Route path="/search" component={SearchPage} />
        <Route path="/books" component={BooksPage} />
        <Route default component={NotFound} />
      </Router>
      <footer class="foot">
        Данные: IMDb (для личного использования), Wikidata, TMDB, Open Library. This product uses the TMDB API
        but is not endorsed or certified by TMDB.
      </footer>
      <Toasts />
    </LocationProvider>
  );
}

render(<App />, document.getElementById("app")!);
