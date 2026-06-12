const endpoints = [
  ["GET", "/data/init", "Bootstrap"],
  ["GET", "/auth-token", "Sesion"],
  ["POST", "https://api.quantummetric.com/query", "GraphQL"],
  ["POST", "/api/graphql", "GraphQL legacy"],
  ["POST", "/analytics", "Widgets"],
  ["POST", "/analytics/historical", "Historicos"],
];

const cards = [
  "Sesiones con conversion",
  "Tiempo medio de sesion",
  "Detalle por APP Name y Sistema operativo",
  "Paginas Vistas",
  "Sesiones",
];

export function AsIsExplorer() {
  return (
    <>
      <header className="page-header">
        <h1>As-Is Explorer</h1>
        <span className="status ok">verificado</span>
      </header>

      <section className="grid cols-2">
        <div className="card">
          <h2>APIs</h2>
          <table className="table">
            <tbody>
              {endpoints.map(([method, path, use]) => (
                <tr key={path}>
                  <td>{method}</td>
                  <td>{path}</td>
                  <td>{use}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="card">
          <h2>Dashboard General MX</h2>
          <table className="table">
            <tbody>
              {cards.map((card) => (
                <tr key={card}>
                  <td>{card}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
