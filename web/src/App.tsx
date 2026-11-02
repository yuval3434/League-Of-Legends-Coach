import { Champions } from "./pages/Champions";
import { Coach } from "./pages/Coach";
import { Compare } from "./pages/Compare";
import { Overview } from "./pages/Overview";
import { useRoute } from "./router";

export default function App() {
  const route = useRoute();
  switch (route.page) {
    case "champions":
      return <Champions />;
    case "compare":
      return <Compare />;
    case "coach":
      return <Coach question={route.params.get("q") ?? ""} />;
    default:
      return <Overview />;
  }
}
