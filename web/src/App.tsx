import { Champions } from "./pages/Champions";
import { Coach } from "./pages/Coach";
import { Compare } from "./pages/Compare";
import { Draft } from "./pages/Draft";
import { Matches } from "./pages/Matches";
import { Overview } from "./pages/Overview";
import { Players } from "./pages/Players";
import { Settings } from "./pages/Settings";
import { useRoute } from "./router";

export default function App() {
  const route = useRoute();
  switch (route.page) {
    case "champions":
      return <Champions />;
    case "compare":
      return <Compare />;
    case "matches":
      return <Matches id={route.params.get("id")} />;
    case "draft":
      return <Draft />;
    case "settings":
      return <Settings />;
    case "players":
      return <Players />;
    case "coach":
      return <Coach question={route.params.get("q") ?? ""} />;
    default:
      return <Overview />;
  }
}
