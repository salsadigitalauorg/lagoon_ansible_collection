import { makeExecutableSchema } from "graphql-tools"
import { importSchema } from 'graphql-import'
import { addMocksToSchema } from '@graphql-tools/mock'
import { createYoga } from 'graphql-yoga';
import { createServer } from 'http'

const typeDefs = importSchema('schema.graphql')
const schema = makeExecutableSchema({ typeDefs })
const schemaWithMocks = addMocksToSchema({ schema })

createServer(
  createYoga({ schema: schemaWithMocks })
).listen(4000, () => {
  console.log('GraphQL Server is listening on http://localhost:4000/graphql');
})
